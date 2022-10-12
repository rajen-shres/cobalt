import logging
import re
from threading import Thread

import boto3
from botocore.exceptions import ClientError
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMultiAlternatives
from django.db import connection
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe
from fcm_django.models import FCMDevice
from firebase_admin.messaging import (
    Message,
    Notification,
    AndroidConfig,
    AndroidNotification,
    APNSConfig,
    APNSPayload,
    Aps,
)
from post_office import mail as po_email

from accounts.models import User, UserAdditionalInfo, UnregisteredUser
from cobalt.settings import (
    COBALT_HOSTNAME,
    DISABLE_PLAYPEN,
    RBAC_EVERYONE,
    DEFAULT_FROM_EMAIL,
    GLOBAL_TITLE,
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION_NAME,
    TBA_PLAYER,
)
from notifications.forms import EmailContactForm
from notifications.models import (
    Snooper,
    BatchID,
    EmailBatchRBAC,
    Email,
    RealtimeNotificationHeader,
    RealtimeNotification,
    InAppNotification,
    UnregisteredBlockedEmail,
)
from organisations.models import Organisation
from rbac.core import rbac_user_has_role

logger = logging.getLogger("cobalt")

# Max no of emails to send in a batch
MAX_EMAILS = 45

# Max number of threads
MAX_EMAIL_THREADS = 20


def _to_address_checker(to_address, context):
    """Check environment to see what the to_address should be. This protects us from sending to
    real users from test environments
    Args:
        to_address(str): email address to verify based upon environment
        context(dict): dict with email_body (hopefully)
    """
    # If DISABLE_PLAYPEN is set, then just return this unmodified, e.g. production
    if DISABLE_PLAYPEN == "ON":
        return to_address, context
    # TODO: Change this to a variable if we ever use anything other than AWS SES
    # https://docs.aws.amazon.com/ses/latest/DeveloperGuide/send-email-simulator.html

    safe_address = "success@simulator.amazonses.com"

    # If the everyone user is set to a valid email then we send to that
    # If still set to the default (a@b.com) then we ignore
    everyone = User.objects.get(pk=RBAC_EVERYONE)

    if everyone.email == "a@b.com":
        return_address = safe_address

        if "email_body" in context:
            context[
                "email_body"
            ] = f"""<h1>Non-production environment<h1>
                                        <h2>This email was not sent</h2>
                                        <h3>To send this in future, update the email address of EVERYONE
                                        from a@b.com to a real email address.</h3>
                                        {context["email_body"]}
                                     """
        logger.warning(
            f"DISABLE_PLAYPEN is OFF. Overriding email address from '{to_address}' to '{return_address}' "
            f"We will use the email address of the EVERYONE user if it is not set to a@b.com."
        )
    else:
        return_address = everyone.email
        logger.warning(
            f"DISABLE_PLAYPEN is OFF. Overriding email address from '{to_address}' to '{return_address}'"
        )
    return return_address, context


def _email_address_on_bounce_list(to_address):
    """Check if we are not sending to this address"""

    # First check if it bounced
    user_additional_info = UserAdditionalInfo.objects.filter(
        user__email=to_address
    ).first()

    un_reg = UnregisteredUser.objects.filter(email=to_address).first()

    if (user_additional_info and user_additional_info.email_hard_bounce) or (
        un_reg and un_reg.email_hard_bounce
    ):
        logger.info(f"Not sending email to suppressed address - {to_address}")
        return True

    # Now check for unregistered users blocking sending
    if UnregisteredBlockedEmail.objects.filter(email=to_address).exists():
        logger.info(f"Not sending email to unregistered user at address - {to_address}")
        return True

    return False


def send_cobalt_email_with_template(
    to_address,
    context,
    template="system - default",
    sender=None,
    priority="medium",
    batch_id=None,
    reply_to=None,
    attachments=None,
):
    """Queue an email using a template and context.

    Args:
        to_address (str or list): who to send to
        context (dict): values to substitute into email template
        template (str or EmailTemplate instance): it is more efficient to use an instance for multiple calls
        sender (str): who to send from (None will use default from settings file)
        priority (str): Django Post Office priority
        batch_id (BatchID): batch_id for this batch of emails
        reply_to (str): email address to send replies to
        attachments (dict): optional dictionary of attachments

    Returns:
        Nothing

    Context for the default template can have:

    img_src: logo to override default MyABF logo
    name: Users first name
    title: Goes in title box
    email_body: main part of email
    additional_words: goes after main body
    link: link for button e.g. /dashboard
    link_text: words to go on link button
    link_colour: default, primary, warning, danger, success, info
    box_colour: default, primary, warning, danger, success, info

    unregistered_identifier: will use alternative footer and show link to unregistered user preferences

    """

    # Check if on bounce list
    if _email_address_on_bounce_list(to_address):
        logger.info(f"Ignoring email on bounce list {to_address}")
        return

    # Augment context
    context["host"] = COBALT_HOSTNAME
    if "img_src" not in context:
        context["img_src"] = "notifications/img/myabf-email.png"
    if "box_colour" not in context:
        context["box_colour"] = "primary"
    if "link_colour" not in context:
        context["link_colour"] = "primary"
    if "subject" not in context and "title" in context:
        context["subject"] = context["title"]

    # mark subject as safe or characters get changed
    if context["subject"]:
        context["subject"] = mark_safe(context["subject"])

    # Check for playpen - don't send emails to users unless on production or similar
    to_address, context = _to_address_checker(to_address, context)

    headers = {"Reply-to": reply_to} if reply_to else None
    email = po_email.send(
        sender=sender,
        recipients=to_address,
        template=template,
        context=context,
        render_on_delivery=True,
        priority=priority,
        headers=headers,
        attachments=attachments,
    )

    Snooper(post_office_email=email, batch_id=batch_id).save()


def send_cobalt_email_preformatted(
    to_address,
    subject,
    msg,
    sender=None,
    priority="medium",
    batch_id=None,
    reply_to=None,
):
    """Queue an email that has already been formatted. Does not use a template.

        Generally, you should use a template, but sometimes this is necessary.

    Args:
        to_address (str or list): who to send to
        subject (str): subject line
        msg (str): HTML message
        sender (str): who to send from (None will use default from settings file)
        priority (str): Django Post Office priority
        batch_id (BatchID): batch_id for this batch of emails
        reply_to (str): email address to send replies to

    Returns:
        Nothing
    """

    # Check if on bounce list
    if _email_address_on_bounce_list(to_address):
        return

    headers = {"Reply-to": reply_to} if reply_to else None

    # Check for playpen - don't send emails to users unless on production or similar
    # We are the poor cousin and don't have a dict to send (which would normally hold
    # email body) so we send a cut down one and convert the response
    to_address, return_dict = _to_address_checker(
        to_address=to_address, context={"email_body": msg}
    )
    msg = return_dict["email_body"]

    email = po_email.send(
        recipients=to_address,
        sender=sender,
        subject=subject,
        html_message=msg,
        priority=priority,
        headers=headers,
    )

    Snooper(post_office_email=email, batch_id=batch_id).save()


def create_rbac_batch_id(
    rbac_role: str,
    batch_id: BatchID = None,
    user: User = None,
    organisation: Organisation = None,
):
    """Create a new EmailBatchRBAC object to allow an RBAC role to access a batch of emails

    Args:
        rbac_role (str): the RBAC role to allow. e.g. "org.orgs.34.view"
        batch_id (BatchID): batch ID, if None a new batch Id will be created
        organisation: Org responsible for sending this
        user: User responsible for sending this

    Returns: BatchID

    """

    if not batch_id:
        batch_id = BatchID()
        batch_id.create_new()
        batch_id.save()

        EmailBatchRBAC(
            batch_id=batch_id,
            rbac_role=rbac_role,
            meta_sender=user,
            meta_organisation=organisation,
        ).save()

    return batch_id


def send_cobalt_bulk_email(bcc_addresses, subject, message, reply_to=""):
    """Sends the same message to multiple people.

    Args:
        bcc_addresses (list): who to send to, list of strings
        subject (str): subject line for email
        message (str): message to send in HTML or plain format
        reply_to (str): who to send replies to

    Returns:
        Nothing
    """

    # start thread
    thread = Thread(
        target=send_cobalt_bulk_email_thread,
        args=[bcc_addresses, subject, message, reply_to],
    )
    thread.setDaemon(True)
    thread.start()


def send_cobalt_bulk_email_thread(bcc_addresses, subject, message, reply_to):
    """Send bulk emails. Asynchronous thread

    Args:
        bcc_addresses (list): who to send to, list of strings
        subject (str): subject line for email
        message (str): message to send in HTML or plain format
        reply_to (str): who to send replies to

    Returns:
        Nothing
    """

    plain_message = strip_tags(message)

    # split emails into chunks using an ugly list comprehension stolen from the internet
    # turn [a,b,c,d] into [[a,b],[c,d]]
    # fmt: off
    emails_as_list = [
        bcc_addresses[i * MAX_EMAILS: (i + 1) * MAX_EMAILS]
        for i in range((len(bcc_addresses) + MAX_EMAILS - 1) // MAX_EMAILS)
    ]
    # fmt: on

    for emails in emails_as_list:

        msg = EmailMultiAlternatives(
            subject,
            plain_message,
            to=[],
            bcc=emails,
            from_email=DEFAULT_FROM_EMAIL,
            reply_to=[reply_to],
        )

        msg.attach_alternative(message, "text/html")

        msg.send()

        for email in emails:
            Email(
                subject=subject,
                message=message,
                recipient=email,
                status="Sent",
            ).save()

    # Django creates a new database connection for this thread so close it
    connection.close()


def send_cobalt_bulk_sms(
    msg_list,
    admin,
    description,
    invalid_lines=None,
    total_file_rows=0,
    from_name=GLOBAL_TITLE,
):
    """Try to send a bunch of SMS messages to users. Will only send if they are registered, want to receive SMS
    and have a valid phone number.

    Args:
        msg_list(list): list of tuples of system number and message to send (system_number, "message")
        admin(User): administrator responsible for sending these messages
        description(str): Text description of this batch of messages
        invalid_lines(list): list of invalid lines in upload file
        from_name(str): Name to use as the sender
        total_file_rows(int): Number of rows in original file

    Returns:
        sent_users(list): Who we think we sent messages to
        unregistered_users(list): list of users who we do not know about
        un_contactable_users(list): list of users who don't have mobiles or haven't ticked to receive SMS
    """

    unregistered_users = []
    uncontactable_users = []
    sent_users = []

    # Log this batch
    header = RealtimeNotificationHeader(
        admin=admin,
        description=description,
        attempted_send_number=len(msg_list),
        invalid_lines=invalid_lines,
        total_record_number=total_file_rows,
    )
    header.save()

    # Get system_numbers as list
    system_numbers = [item[0] for item in msg_list]

    # Get the users who want to be contacted and have phone numbers
    users = (
        User.objects.filter(system_number__in=system_numbers)
        .filter(receive_sms_results=True)
        .filter(mobile__isnull=False)
    )

    # Get the users who are in the system
    registered_users = User.objects.filter(
        system_number__in=system_numbers
    ).values_list("system_number", flat=True)
    registered_users = list(registered_users)

    # Create dict of ABF number to phone number
    phone_lookup = {}
    user_lookup = {}
    for user in users:
        # Convert to international
        phone_lookup[user.system_number] = f"+61{user.mobile[1:]}"
        user_lookup[user.system_number] = user

    for item in msg_list:
        system_number, msg = item

        # See if we can send this
        if system_number not in phone_lookup:
            if (
                system_number in registered_users
            ):  # This one is registered but not contactable
                uncontactable_users.append(system_number)
            else:  # This one is not registered
                unregistered_users.append(system_number)
            continue

        user = user_lookup[system_number]

        phone_number = phone_lookup[item[0]]
        msg = item[1]

        # Send it
        send_cobalt_sms(
            phone_number=phone_number,
            msg=msg,
            from_name=from_name,
            header=header,
            member=user,
        )

        sent_users.append(system_number)

    # Update header
    header.send_status = bool(sent_users)
    header.successful_send_number = len(sent_users)

    # Save lists as strings using model functions
    header.set_uncontactable_users(uncontactable_users)
    header.set_unregistered_users(unregistered_users)
    header.set_invalid_lines(invalid_lines)
    header.save()

    return sent_users, unregistered_users, uncontactable_users


def send_cobalt_sms(
    phone_number, msg, from_name=GLOBAL_TITLE, header=None, member=None
):
    """Send single SMS. This will be replaced with a mobile app later

    Args:
        phone_number (str): who to send to
        msg (str): message to send
        from_name(str): Display name of sender
        header(RealtimeNotificationHeader): parent for this message
        member(User): user for this message

    Returns:
        None
    """

    # from_name must be alpha-numeric or hyphens only, must start and end with alphanumeric, 11 chars max
    if len(from_name) > 11:
        from_name = from_name[:11]

    # replace non alphanumerics with -
    from_name = re.sub("[^0-9a-zA-Z]+", "-", from_name)

    # Check start and end
    if from_name[0] == "-":
        from_name[0] = "A"
    if len(from_name) == 11 and from_name[10] == "-":
        from_name[10] = "A"

    client = boto3.client(
        "sns",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION_NAME,
    )

    # Assume the worst
    return_code = False

    try:
        return_values = client.publish(
            PhoneNumber=phone_number,
            Message=msg,
            MessageAttributes={
                "AWS.SNS.SMS.SenderID": {
                    "DataType": "String",
                    "StringValue": from_name,
                },
                "AWS.SNS.SMS.SMSType": {
                    "DataType": "String",
                    "StringValue": "Transactional",
                },
            },
        )

        if return_values["ResponseMetadata"]["HTTPStatusCode"] == 200:
            return_code = True

    except ClientError:
        logger.exception(f"Couldn't publish message to {phone_number}")

    # Log it
    RealtimeNotification(
        member=member,
        admin=header.admin,
        status=return_code,
        msg=msg,
        header=header,
        aws_message_id=return_values["MessageId"],
    ).save()


def contact_member(
    member,
    msg,
    contact_type="Email",
    link=None,
    link_text="View",
    html_msg=None,
    subject=None,
):
    """Contact member using email or SMS. In practice, always Email.

    This is for simple cases:

    It uses the default template with a link. If you don't provide the link it will looks silly.
    msg = short description to go on the in-app notification
    subject is also used as the title (inside body of email)

    """

    # Ignore system accounts
    if member.id in (RBAC_EVERYONE, TBA_PLAYER):
        return

    if not subject:
        subject = "Notification from My ABF"

    if not html_msg:
        html_msg = msg

    # Always create an in app notification
    add_in_app_notification(member, msg, link)

    if contact_type == "Email":
        context = {
            "name": member.first_name,
            "title": subject,
            "email_body": html_msg,
            "link": link,
            "link_text": link_text,
        }

        send_cobalt_email_with_template(to_address=member.email, context=context)

    if contact_type == "SMS":
        send_cobalt_sms(member.mobile, msg)


def add_in_app_notification(member, msg, link=None):
    """Add a notification to the menu bar telling a user they have a message"""

    InAppNotification(member=member, message=msg[:100], link=link).save()


@login_required()
def email_contact(request, member_id):
    """email contact form"""

    member = get_object_or_404(User, pk=member_id)

    form = EmailContactForm(request.POST or None)

    if request.method == "POST":
        title = request.POST["title"]
        message = request.POST["message"].replace("\n", "<br>")
        msg = f"""
                  Email from: {request.user} ({request.user.email})<br><br>
                  <b>{title}</b>
                  <br><br>
                  {message}
        """

        context = {
            "name": member.first_name,
            "title": f"Email from: {request.user.full_name}",
            "email_body": msg,
        }

        send_cobalt_email_with_template(
            to_address=member.email,
            context=context,
            reply_to=request.user.email,
        )

        messages.success(
            request,
            "Message sent successfully",
            extra_tags="cobalt-message-success",
        )

        redirect_to = request.POST.get("redirect_to", "dashboard:dashboard")
        return redirect(redirect_to)

    return render(
        request, "notifications/email_form.html", {"form": form, "member": member}
    )


def _cloudwatch_reader(log_group, notification):
    """Get data from Cloudwatch"""

    client = boto3.client(
        "logs",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION_NAME,
    )

    filter_pattern = f'{{ $.notification.messageId = "{notification.aws_message_id}" }}'

    # TODO: Start and end times need investigated. Probably okay not to use them.
    # start_time = int((datetime.now() - timedelta(hours=240)).timestamp()) * 1000
    # end_time = int((datetime.now() + timedelta(hours=240)).timestamp()) * 1000

    # It is possible to get multiple messages and to need a cursor (nextToken) to get all messages
    # Get first response
    response = client.filter_log_events(
        logGroupName=log_group,
        # startTime=start_time,
        # endTime=end_time,
        filterPattern=filter_pattern,
    )

    results = response["events"]

    # Continue to build results if we got a nextToken
    while "nextToken" in response:
        response = client.filter_log_events(
            logGroupName=log_group,
            # startTime=start_time,
            # endTime=end_time,
            filterPattern=filter_pattern,
            nextToken=response["nextToken"],
        )
        results.extend(response["events"])

    return results


@login_required()
def send_test_fcm_message(request, fcm_device_id):
    """Send a test message to a users registered FCM device"""

    fcm_device = FCMDevice.objects.filter(pk=fcm_device_id).first()

    # Check access
    if fcm_device and (
        fcm_device.user == request.user
        or rbac_user_has_role(member=request.user, role="notifications.admin.view")
    ):
        now = timezone.localtime().strftime("%a %d-%b-%Y %-I:%M")
        now += timezone.localtime().strftime("%p").lower()

        test_msg = (
            f"This is a test message.\n\n"
            f"It was sent to {fcm_device.user}.\n\n"
            f"It was sent by {request.user}.\n\n"
            f"It was sent on {now}."
        )

        rc = send_fcm_message(fcm_device, test_msg, request.user)

        return HttpResponse(f"Message sent {rc}")

    return HttpResponse("Device not found or access denied")


def send_fcm_message(fcm_device, msg, admin=None):
    """Send a message to a users registered FCM device"""

    if not admin:
        admin = User.objects.get(pk=RBAC_EVERYONE)

    RealtimeNotification(member=fcm_device.user, admin=admin, msg=msg).save()

    msg = Message(
        notification=Notification(
            title=f"Test Message for {fcm_device.user.first_name}", body=msg
        ),
        android=AndroidConfig(
            priority="high",
            notification=AndroidNotification(sound="default", default_sound=True),
        ),
        apns=APNSConfig(
            payload=APNSPayload(
                aps=Aps(sound="default"),
            ),
        ),
    )

    rc = fcm_device.send_message(msg)
    logger.info(rc)

    return rc


def send_cobalt_email_to_system_number(
    system_number, subject, message, club=None, administrator=None
):
    """Generic function to send a simple email to a user or unregistered user

    if we get a club then we will use that to look for club specific email addresses

    """

    from accounts.views.core import (
        get_email_address_and_name_from_system_number,
    )

    email_address, first_name = get_email_address_and_name_from_system_number(
        system_number, club
    )
    if not email_address:
        logger.warning(
            f"Unable to send email to {system_number}. No email address found."
        )
        return

    un_registered_user = UnregisteredUser.objects.filter(
        system_number=system_number
    ).first()
    if un_registered_user:
        unregistered_identifier = un_registered_user.identifier
    else:
        unregistered_identifier = None

    context = {
        "box_colour": "#00bcd4",
        "name": first_name,
        "title": subject,
        "email_body": message,
        "img_src": "/static/notifications/img/myabf-email.png",
        "unregistered_identifier": unregistered_identifier,
    }

    if club:
        # Create batch id so admins can see this email
        batch_id = create_rbac_batch_id(
            rbac_role=f"notifications.orgcomms.{club.id}.edit",
            user=administrator,
            organisation=club,
        )
    else:
        batch_id = None

    send_cobalt_email_with_template(
        to_address=email_address,
        context=context,
        batch_id=batch_id,
        template="system - club",
    )
