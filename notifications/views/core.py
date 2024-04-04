import logging
import re
import mimetypes
from threading import Thread
from itertools import chain

import boto3
import firebase_admin.messaging
from botocore.exceptions import ClientError
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMultiAlternatives
from django.core.paginator import Paginator
from django.db import connection, IntegrityError
from django.db.models import Count, OuterRef, Subquery, CharField
from django.db.models.functions import Cast
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
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
    ALL_SYSTEM_ACCOUNTS,
    apply_large_email_batch_config,
)
from events.models import (
    CongressMaster,
    Congress,
    Event,
    EventEntryPlayer,
)

from notifications.forms import (
    EmailContactForm,
    EmailOptionsForm,
    EmailContentForm,
    EmailAttachmentForm,
    AddContactForm,
)
from notifications.models import (
    Snooper,
    BatchID,
    BatchActivity,
    BatchContent,
    BatchAttachment,
    EmailBatchRBAC,
    Email,
    EmailAttachment,
    RealtimeNotificationHeader,
    RealtimeNotification,
    Recipient,
    InAppNotification,
    UnregisteredBlockedEmail,
)
from organisations.models import (
    Organisation,
    MemberClubEmail,
    ClubTag,
    MemberClubTag,
    MemberMembershipType,
    OrgEmailTemplate,
)
from organisations.decorators import check_club_menu_access
from rbac.core import rbac_user_has_role, rbac_get_users_with_role

from post_office.models import Email as PostOfficeEmail

logger = logging.getLogger("cobalt")

# Max no of emails to send in a batch
MAX_EMAILS = 45

# Max number of threads
MAX_EMAIL_THREADS = 20

# Artificial id for EVERYONE club tag
EVERYONE_TAG_ID = 9999999


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

    un_reg = MemberClubEmail.objects.filter(email=to_address).first()

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
    batch_size=1,
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
        boolean: True if the message was sent, False otherwise

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

    print("+-----------------------------------+")
    print("|  send_cobalt_email_with_template  |")
    print("+-----------------------------------+")
    print(f"   to_address      : {to_address}")
    print("   context         :")
    for context_key in context:
        print(f"                   : {context_key} : {context[context_key]}")
    print(f"   template        : {template} [type={type(template)}]")
    print(f"                   : [type={type(template)}]")
    print(f"   sender          : {sender if sender else 'None'}")
    print(f"   priority        : {priority}")
    print(f"   batch_id        : {batch_id if batch_id else 'None'}")
    print(f"   reply_to        : {reply_to if reply_to else 'None'}")
    print(
        f"   attachments     : {('#=' + {len(attachments)}) if attachments else 'None'}"
    )
    print(f"   batch_size      : {batch_size}")
    print("=====================================")

    # Check if on bounce list
    if _email_address_on_bounce_list(to_address):
        logger.info(f"Ignoring email on bounce list {to_address}")
        return False

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

    # COB-793 - add custom header with batch size
    headers = {"X-Myabf-Batch-Size": batch_size}

    limited_notifications = apply_large_email_batch_config(batch_size)
    if limited_notifications:
        logger.debug(f"Email is part of a large batch of {batch_size}")

    if reply_to:
        headers["Reply-to"] = reply_to

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

    Snooper(
        post_office_email=email,
        batch_id=batch_id,
        limited_notifications=limited_notifications,
    ).save()

    return True


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
    batch_type: str = "UNK",
    batch_size: int = 0,
    description: str = None,
    complete: bool = False,
):
    """Create a new EmailBatchRBAC object to allow an RBAC role to access a batch of emails

    Updated in sprint-48 to add type and description

    Args:
        rbac_role (str): the RBAC role to allow. e.g. "org.orgs.34.view"
        batch_id (BatchID): batch ID, if None a new batch Id will be created
        organisation: Org responsible for sending this
        user: User responsible for sending this
        batch_type: Type of batch (BatchID.BATCH_TYPE)
        description: Email subject line or description

    Returns: BatchID

    """

    if not batch_id:
        batch_id = BatchID()
        batch_id.create_new()
        batch_id.batch_type = batch_type
        batch_id.batch_size = batch_size
        batch_id.description = description if description else "New email batch"
        batch_id.state = (
            BatchID.BATCH_STATE_COMPLETE if complete else BatchID.BATCH_STATE_WIP
        )
        batch_id.organisation = organisation
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


def send_cobalt_bulk_notifications(
    msg_list,
    admin,
    description,
    invalid_lines=None,
    total_file_rows=0,
    sender_identification=None,
):
    """This originally sent messages over SMS, but now we only support FCM.

    Args:
        sender_identification(str): e.g. Compscore licence number to identify the sender
        msg_list(list): list of tuples of system number and message to send (system_number, "message")
        admin(User): administrator responsible for sending these messages
        description(str): Text description of this batch of messages
        invalid_lines(list): list of invalid lines in upload file
        total_file_rows(int): Number of rows in original file

    Returns:
        sent_users(list): Who we think we sent messages to
        unregistered_users(list): list of users who we do not know about
        fcm_users(list): list of users we sent FCM messages to. Users may have multiple devices registered
        un_contactable_users(list): list of users who don't have mobiles or haven't ticked to receive SMS
    """

    unregistered_users = []
    uncontactable_users = []
    sent_users = []

    # For now we just store the users, could change this to store users and devices, for non-blank headers this can be
    # worked out anyway
    fcm_sent_users = []
    fcm_failed_users = []

    # Log this batch
    header = RealtimeNotificationHeader(
        admin=admin,
        description=description,
        attempted_send_number=len(msg_list),
        invalid_lines=invalid_lines,
        total_record_number=total_file_rows,
        sender_identification=sender_identification,
    )
    header.save()

    # load data

    app_users, fcm_lookup = _send_cobalt_bulk_notification_get_data(msg_list)

    # Go through and try to send the messages
    for item in msg_list:
        system_number, msg = item
        # Reformat string
        msg = msg.replace("<br>", "\n")

        fcm_device_list = fcm_lookup.get(system_number)
        if fcm_device_list:
            # If it works for any device, count that as successful
            worked = False

            for index, fcm_device in enumerate(fcm_device_list):
                # Only add the first message to the database
                add_message_to_database = index == 0
                if send_fcm_message(
                    fcm_device, msg, admin, header, add_message_to_database
                ):
                    worked = True

            if worked:
                fcm_sent_users.append(system_number)
            else:
                fcm_failed_users.append(system_number)
                uncontactable_users.append(system_number)

        else:
            unregistered_users.append(system_number)

    # Update header
    header.send_status = bool(sent_users + fcm_sent_users)
    header.successful_send_number = len(sent_users) + len(fcm_sent_users)

    # Save lists as strings using model functions
    header.set_uncontactable_users(uncontactable_users)
    header.set_unregistered_users(unregistered_users)
    header.set_invalid_lines(invalid_lines)
    header.save()

    return sent_users + fcm_sent_users, unregistered_users, uncontactable_users


def _send_cobalt_bulk_notification_get_data(msg_list):
    """sub of send_cobalt_bulk_notifications to load required data"""

    # Get system_numbers as list
    system_numbers = [item[0] for item in msg_list]

    # Get the App users (people set up with FCM)
    app_users = FCMDevice.objects.filter(
        user__system_number__in=system_numbers
    ).select_related("user")

    # create dict of ABF number to FCM, can be multiple devices per person
    fcm_lookup = {}
    for app_user in app_users:
        if app_user.user.system_number not in fcm_lookup:
            fcm_lookup[app_user.user.system_number] = []
        fcm_lookup[app_user.user.system_number].append(app_user)

    return app_users, fcm_lookup


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
    batch_id=None,
):
    """Contact member using email or SMS. In practice, always Email.

    This is for simple cases:

    It uses the default template with a link. If you don't provide the link it will looks silly.
    msg = short description to go on the in-app notification
    subject is also used as the title (inside body of email)

    batch_id is am option BatchID object for use when sending entry related emails

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

        send_cobalt_email_with_template(
            to_address=member.email, context=context, batch_id=batch_id
        )

    if contact_type == "SMS":
        raise PermissionError("SMS not supported any more")


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

        send_fcm_message(fcm_device, test_msg, request.user)

        return HttpResponse("Message sent")

    return HttpResponse("Device not found or access denied")


def send_fcm_message(
    fcm_device, msg, admin=None, header=None, add_message_to_database=True
):
    """Send a message to a users registered FCM device"""

    if not admin:
        admin = User.objects.get(pk=RBAC_EVERYONE)

    if add_message_to_database:
        # For people with multiple devices we only add the message to the database once
        RealtimeNotification(
            member=fcm_device.user,
            admin=admin,
            msg=msg,
            header=header,
            fcm_device=fcm_device,
        ).save()

    msg = Message(
        notification=Notification(
            title=f"Message for {fcm_device.user.first_name}", body=msg
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

    # Try to send the message, handle any error, so we don't break the whole sending group
    try:
        rc = fcm_device.send_message(msg)
    except Exception as exc:
        logger.error(exc.__str__())
        return False

    # log it
    if type(rc) is firebase_admin.messaging.SendResponse:
        logger.info(f"Sent message to {fcm_device.user} on device: {fcm_device.name}")
        return True

    # If we get an error then handle it
    else:
        logger.error(f"Error from FCM for {fcm_device.user} - {rc}")
        logger.error(f"Deleting FCM device {fcm_device.name} for {fcm_device.user}")
        fcm_device.delete()
        return False


def send_cobalt_email_to_system_number(
    system_number, subject, message, club=None, administrator=None
):
    """Generic function to send a simple email to a user or unregistered user

    if we get a club then we will use that to look for club specific email addresses

    Updated for sprint-48 to pass additional header information to BatchID
    Note: all emails sent via this function with a club specified are assumed to
    be of batch_type Admin.
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
            batch_type=BatchID.BATCH_TYPE_ADMIN,
            batch_size=1,
            description=subject,
            complete=True,
        )
    else:
        batch_id = None

    send_cobalt_email_with_template(
        to_address=email_address,
        context=context,
        batch_id=batch_id,
        template="system - club",
    )


def remove_email_from_blocked_list(email_address):
    """Remove an email address from our internal list of blocked addresses"""

    users = User.objects.filter(email=email_address)

    for user in users:
        user_additional_info, _ = UserAdditionalInfo.objects.get_or_create(user=user)
        user_additional_info.email_hard_bounce = False
        user_additional_info.email_hard_bounce_reason = None
        user_additional_info.email_hard_bounce_date = None
        user_additional_info.save()

    un_regs = MemberClubEmail.objects.filter(email=email_address)

    for un_reg in un_regs:
        un_reg.email_hard_bounce = False
        un_reg.email_hard_bounce_reason = None
        un_reg.email_hard_bounce_date = None
        un_reg.save()


def get_notifications_statistics():
    """get stats about notifications. Called by util statistics"""

    total_emails = PostOfficeEmail.objects.count()
    total_real_time_notifications = RealtimeNotification.objects.count()
    total_fcm_notifications = RealtimeNotification.objects.filter(
        fcm_device__isnull=False
    ).count()
    total_sms_notifications = total_real_time_notifications - total_fcm_notifications
    total_registered_fcm_devices = FCMDevice.objects.count()

    return {
        "total_emails": total_emails,
        "total_real_time_notifications": total_real_time_notifications,
        "total_sms_notifications": total_sms_notifications,
        "total_fcm_notifications": total_fcm_notifications,
        "total_registered_fcm_devices": total_registered_fcm_devices,
    }


def _add_user_to_recipients(club, batch, user, initial=True):
    """Add a user to the recipients of a batch.

    Returns a tuple of (number added, message string)

    If the user is already a recipient, set as included"""

    recipients = Recipient.objects.filter(batch=batch, system_number=user.system_number)

    if recipients.exists():
        recipient = recipients.first()
        if not recipient.include:
            recipient.include = True
            recipient.save()
            return (1, f"{user.full_name} included")
        return (0, f"{user.full_name} already included")
    else:
        recipient = Recipient()
        recipient.create_from_user(batch, user, initial=initial)
        recipient.save()
        return (1, f"{user.full_name} added")


def _add_contact_to_recipients(batch, first_name, last_name, email):
    """Add a new contact to the recipients of a batch

    Checks whether the email is already in the list and reincludes
    it if already presenet but not incuded.

    Returns success and a user message
    """

    existing = Recipient.objects.filter(batch=batch, email=email).first()
    if existing:
        if existing.include:
            return (False, f"{email} is already in the list")
        else:
            existing.include = True
            existing.save()
            return (True, f"{email} included")

    recipient = Recipient()
    recipient.batch = batch
    recipient.first_name = first_name
    recipient.last_name = last_name
    recipient.email = email
    recipient.include = True
    recipient.initial = False
    recipient.save()

    return (True, f"{email} added")


def _add_to_recipient_with_system_number(batch, club, system_number):
    """Add a user or unregistered user to the batch

    Returns 1 if the user has been added or reincluded, 0 otherwise
    Returns a user message
    """

    #  is the system number already a recipient?
    existing = Recipient.objects.filter(
        batch=batch, system_number=system_number
    ).first()

    if existing:
        print("--- found")
        if existing.include:
            return (0, "Recipient already included")
        else:
            existing.include = True
            existing.save()
            return (1, "Recipient added")

    # is this a User or UnregisteredUser
    user = User.objects.filter(system_number=system_number).first()

    if user:
        recipient = Recipient()
        recipient.system_number = system_number
        recipient.batch = batch
        recipient.first_name = user.first_name
        recipient.last_name = user.last_name
        recipient.email = user.email
        recipient.include = True
        recipient.initial = False
        recipient.save()
        return (1, "Recipient added")

    else:
        # is not a user, so try an unregistered club member

        member_email = MemberClubEmail.objects.filter(
            organisation=club, system_number=system_number
        ).first()

        if member_email and member_email.email:
            # still need to get the unregistered user record to get the user name
            unreg = UnregisteredUser.objects.filter(system_number=system_number).first()

            recipient = Recipient()
            recipient.system_number = system_number
            recipient.batch = batch
            recipient.first_name = unreg.first_name
            recipient.last_name = unreg.last_name
            recipient.email = member_email.email
            recipient.include = True
            recipient.initial = False
            recipient.save()
            return (1, "Recipient added")

        else:
            return (0, "Recipient not found")


def compose_club_email(request, club_id):
    """Entry point for starting a new club batch email

    Just create the batchId and then start the composition flow"""

    # JPG TO DO Security

    club = get_object_or_404(Organisation, pk=club_id)

    # let anyone with comms access to this org view them
    batch = create_rbac_batch_id(
        rbac_role=f"notifications.orgcomms.{club.id}.edit",
        user=request.user,
        organisation=club,
        batch_type=BatchID.BATCH_TYPE_COMMS,
        description=f"Email to {club} members",
        complete=False,
    )

    return redirect("notifications:compose_email_recipients", club_id, batch.id)


def initiate_admin_multi_email(request, club_id):
    """Entry point for multi congress / event selection view

    Just create the batch record and start the composition process"""

    # JPG TO DO SECURITY

    org = get_object_or_404(Organisation, pk=club_id)

    # create the batch header
    batch = create_rbac_batch_id(
        f"events.org.{club_id}.view",
        organisation=org,
        batch_type=BatchID.BATCH_TYPE_MULTI,
        batch_size=0,
        description=f"Email to entrants of {org} events",
        complete=False,
    )

    # go to club menu, comms tab, edit batch
    return redirect("notifications:compose_email_multi_select", club_id, batch.id)


@login_required()
def compose_email_multi_select(request, club_id, batch_id_id):
    """Compose batch emails - step 0 - select events (multis only)"""

    # JPG TO DO SECURITY

    club = get_object_or_404(Organisation, pk=club_id)
    batch = get_object_or_404(BatchID, pk=batch_id_id)

    masters = CongressMaster.objects.filter(org=club)

    if request.method == "POST":
        # update the selected batch activities and rebuild the recipients

        print("POST recieved")

        # delete existing activities and recipients
        BatchActivity.objects.filter(batch=batch).delete()

        Recipient.objects.filter(batch=batch).delete()

        # build a list of all of the events selected, and add the activities
        event_ids = []
        for key, value in request.POST.items():
            if key == "csrfmiddlewaretoken" or key == "select-all":
                continue
            print(f"{key} : {value} ({type(value)})")
            parts = key.split("-")
            activity = BatchActivity(batch=batch, activity_id=int(value))
            if parts[0] == "event":
                activity.activity_type = BatchActivity.ACTIVITY_TYPE_EVENT
                event_ids.append(int(value))
            elif parts[0] == "congress":
                activity.activity_type = BatchActivity.ACTIVITY_TYPE_CONGRESS
                congress = get_object_or_404(Congress, pk=int(value))
                event_ids += congress.event_set.all().values_list("id", flat=True)
            elif parts[0] == "master":
                activity.activity_type = BatchActivity.ACTIVITY_TYPE_SERIES
                master = get_object_or_404(CongressMaster, pk=int(value))
                for congress in master.congress_set.all():
                    event_ids += congress.event_set.all().values_list("id", flat=True)
            activity.save()
            print(
                f"Activity created: {activity.get_activity_type_display()} {activity.activity_id}"
            )

        # add the reciepients for the events
        added_count = 0
        for event_id in event_ids:
            event = Event.objects.get(pk=event_id)
            entered_players = EventEntryPlayer.objects.filter(
                event_entry__event=event
            ).select_related("player")
            for entered_player in entered_players:
                if entered_player.player.system_number not in ALL_SYSTEM_ACCOUNTS:
                    recipient = Recipient()
                    recipient.create_from_user(batch, entered_player.player)
                    try:
                        recipient.save()
                        added_count += 1
                    except IntegrityError:
                        # ignore duplicate system_numbers within the batch
                        pass

        if added_count > 0:
            # and redirect to the next step

            return redirect(
                "notifications:compose_email_recipients", club_id, batch_id_id
            )
        else:
            messages.add_message(request, messages.INFO, "No entrants found")

    else:
        # build the view from the selected batch activities

        print("Not POST")

        activities = BatchActivity.objects.filter(
            batch=batch,
        ).all()

        selected_masters = [
            activity.activity_id
            for activity in activities
            if activity.activity_type == BatchActivity.ACTIVITY_TYPE_SERIES
        ]
        selected_congresses = [
            activity.activity_id
            for activity in activities
            if activity.activity_type == BatchActivity.ACTIVITY_TYPE_CONGRESS
        ]
        selected_events = [
            activity.activity_id
            for activity in activities
            if activity.activity_type == BatchActivity.ACTIVITY_TYPE_EVENT
        ]

        print(f"Selected masters = {selected_masters}")
        print(f"Selected congresses = {selected_congresses}")
        print(f"Selected events = {selected_events}")

    return render(
        request,
        "notifications/batch_email_multi_event.html",
        {
            "step": 0,
            "batch": batch,
            "club": club,
            "masters": masters,
            "selected_masters": selected_masters,
            "selected_congresses": selected_congresses,
            "selected_events": selected_events,
            "existing_selection": (
                len(selected_masters) + len(selected_congresses) + len(selected_events)
            )
            > 0,
        },
    )


@login_required()
def compose_email_recipients(request, club_id, batch_id_id):
    """Compose batch emails - step 1 - review recipients"""

    # JPG TO DO SECURITY

    club = get_object_or_404(Organisation, pk=club_id)
    batch = get_object_or_404(BatchID, pk=batch_id_id)

    congress_stream = batch.batch_type in [
        BatchID.BATCH_TYPE_CONGRESS,
        BatchID.BATCH_TYPE_EVENT,
        BatchID.BATCH_TYPE_MULTI,
    ]

    # Should the add contact form be shown or hidden
    show_contact_form = False

    if request.method == "POST":
        page_number = 1
        add_contact_form = AddContactForm(request.POST)
        if add_contact_form.is_valid():
            success, feedback = _add_contact_to_recipients(
                batch,
                add_contact_form.cleaned_data["first_name"],
                add_contact_form.cleaned_data["last_name"],
                add_contact_form.cleaned_data["email"],
            )
            messages.add_message(request, messages.INFO, feedback)
            if success:
                add_contact_form = AddContactForm()
            else:
                show_contact_form = True
        else:
            messages.add_message(request, messages.INFO, "Error in contact details")
            show_contact_form = True
    elif request.method == "GET":
        add_contact_form = AddContactForm()
        try:
            page_number = int(request.GET.get("page"))
        except ValueError:
            page_number = 1
    else:
        page_number = 1
        add_contact_form = AddContactForm()

    # get all of the recients for the batch and paginate
    recipients = Recipient.objects.filter(
        batch=batch,
    ).order_by("initial", "last_name", "first_name")

    # JPG TO DO - increase for release
    page_size = 10
    pages = Paginator(recipients, page_size)
    page = pages.get_page(page_number)

    # work out where the added and initial headers should be placed on the current page

    added_count = Recipient.objects.filter(batch=batch, initial=False).count()
    initial_count = Recipient.objects.filter(batch=batch, initial=True).count()
    if added_count == 0 or initial_count == 0:
        initial_header_before_row = None
        added_header_before_row = None
    else:
        first_row_on_page = (page_number - 1) * page_size + 1
        last_row_on_page = min(
            (initial_count + added_count), first_row_on_page + page_size - 1
        )
        if added_count <= first_row_on_page:
            #  have paged past the beginning of the initial selection, so show a header
            initial_header_before_row = 1
            added_header_before_row = None
        else:
            # top of page is in the added section, so show a header
            added_header_before_row = 1
            if added_count < last_row_on_page:
                initial_header_before_row = added_count - first_row_on_page + 1
            else:
                initial_header_before_row = None

    # determine range of pages to show in pagination row
    # JPG TO DO - no longer required?

    half_span = 4
    # the number of pages to the left and right if in the middle of a large number of pages
    full_span = half_span * 2 + 1

    if pages.num_pages <= full_span:
        # simple case - able to show all pages at once
        page_range = range(1, pages.num_pages + 1)
    else:
        if page_number <= (half_span + 1):
            # near the beginning
            page_range = range(1, full_span + 1)
        elif page_number >= (pages.num_pages - half_span - 1):
            # near the end
            page_range = range(pages.num_pages - full_span + 1, pages.num_pages + 1)
        else:
            # in the middle
            page_range = range(page_number - half_span, page_number + half_span + 1)

    return render(
        request,
        "notifications/batch_email_recipients.html",
        {
            "step": 1,
            "batch": batch,
            "club": club,
            "page": page,
            "page_range": page_range,
            "allow_contacts": False,  # NOTE - disable until contacts implememnted
            "initial_header_before_row": initial_header_before_row,
            "added_header_before_row": added_header_before_row,
            "add_contact_form": add_contact_form,
            "show_contact_form": show_contact_form,
            "congress_stream": congress_stream,
        },
    )


@login_required()
def compose_email_recipients_add_self(request, club_id, batch_id_id):
    """Add current user to the recipient list"""

    # JPG TO DO SECURITY

    club = get_object_or_404(Organisation, pk=club_id)
    batch = get_object_or_404(BatchID, pk=batch_id_id)

    _, feedback = _add_user_to_recipients(club, batch, request.user, initial=False)
    messages.add_message(request, messages.INFO, feedback)

    return redirect("notifications:compose_email_recipients", club_id, batch_id_id)


@login_required
def compose_email_recipients_add_congress_email(request, club_id, batch_id_id):
    """Add the congress contact email(s) to the recipient list"""

    # JPG TO DO SECURITY

    print("=== compose_email_recipients_add_congress_email ===")

    # club = get_object_or_404(Organisation, pk=club_id)
    batch = get_object_or_404(BatchID, pk=batch_id_id)

    # build a list of congress email addresses from batch activities
    congress_emails = []
    for activity in batch.activities.all():
        email = None
        if activity.activity_type == BatchActivity.ACTIVITY_TYPE_CONGRESS:
            congress = get_object_or_404(Congress, pk=activity.activity_id)
            email = congress.contact_email
        elif activity.activity_type == BatchActivity.ACTIVITY_TYPE_EVENT:
            event = get_object_or_404(Event, pk=activity.activity_id)
            email = event.congress.contact_email
        if email:
            if email not in congress_emails:
                congress_emails.append(email)

    # add the contact emails as recipients
    added_count = 0
    for email in congress_emails:

        already_in = Recipient.objects.filter(email=email)

        if already_in.exists():
            # exists, but make sure that it is included
            recipient = already_in.first()
            if not recipient.include:
                recipient.include = True
                recipient.save()
                added_count += 1
        else:
            # add it
            recipient = Recipient()
            recipient.batch = batch
            recipient.email = email
            recipient.first_name = None
            recipient.last_name = "Contact Email"
            recipient.system_number = None
            recipient.include = True
            recipient.initial = False
            recipient.save()
            added_count += 1

    if added_count == 0:
        messages.add_message(request, messages.WARNING, "No contact emails added")
    else:
        messages.add_message(
            request,
            messages.INFO,
            f"{added_count} contact email{'s' if added_count > 1 else ''} added",
        )

    print(f"=== {added_count} added ===")

    return redirect("notifications:compose_email_recipients", club_id, batch_id_id)


def compose_email_recipients_add_tadmins(request, club_id, batch_id_id):
    """Add club tournament organisers to the recipients"""

    # JPG TO DO SECURITY

    club = get_object_or_404(Organisation, pk=club_id)
    batch = get_object_or_404(BatchID, pk=batch_id_id)

    tournament_admins = rbac_get_users_with_role(f"events.org.{club_id}.edit")

    added_count = 0

    for td in tournament_admins:
        delta, _ = _add_user_to_recipients(club, batch, td, initial=False)
        added_count += delta

    if added_count == 0:
        messages.add_message(request, messages.WARNING, "No tournament admins added")
    else:
        messages.add_message(
            request,
            messages.INFO,
            f"{added_count} tournament admin{'s' if added_count > 1 else ''} added",
        )

    return redirect("notifications:compose_email_recipients", club_id, batch_id_id)


def compose_email_recipients_toggle_recipient_htmx(request, recipient_id):
    """Toggle the include state of the recipient"""

    # JPG TO DO SECURITY

    recipient = get_object_or_404(Recipient, pk=recipient_id)
    recipient.include = not recipient.include
    recipient.save()

    return HttpResponse(status=204)


def compose_email_recipients_remove_unselected_htmx(request, club_id, batch_id_id):
    """Remove all unselected recipients from a batch"""

    # JPG TO DO SECURITY

    # club = get_object_or_404(Organisation, pk=club_id)
    batch = get_object_or_404(BatchID, pk=batch_id_id)

    Recipient.objects.filter(batch=batch, include=False).delete()

    return redirect("notifications:compose_email_recipients", club_id, batch_id_id)


def compose_email_recipients_tags_pane_htmx(request, club_id, batch_id_id):
    """Display the club tags pane in the add recipient view

    Note: This code generates counts of members by tag, regardless of
    whether the member has an email (either as a User or and UnregisteredUser
    with a club email). This could confuse users, eg adding a tag with N members
    but having less than N recipients added to the list.
    """

    # JPG TO DO SECURITY

    club = get_object_or_404(Organisation, pk=club_id)
    batch = get_object_or_404(BatchID, pk=batch_id_id)

    total_members = (
        MemberMembershipType.objects.filter(membership_type__organisation=club)
        .distinct("system_number")
        .count()
    )

    if total_members:
        club_tags = (
            ClubTag.objects.filter(organisation=club)
            .annotate(member_count=Count("memberclubtag"))
            .order_by("tag_name")
        )
        tags = [(EVERYONE_TAG_ID, "Everyone", total_members)] + [
            (tag.id, tag.tag_name, tag.member_count) for tag in club_tags.all()
        ]
    else:
        # no point listing the tags if there are no members
        tags = []

    return render(
        request,
        "notifications/batch_email_recipients_tags_htmx.html",
        {
            "club": club,
            "batch": batch,
            "tags": tags,
        },
    )


def compose_email_recipients_member_search_htmx(request, club_id, batch_id_id):
    """Returns a list of club member search candidates

    Searches by first name, last name or system number (not a combination)
    Matches on teh start of the relevent field, and can include members
    with no club email address (unregistered users).

    Such unregsistered users will be shown in teh UI without a link.
    It may be less confusing if a known member is on teh list but
    not selectable, rather than not there at all.
    """

    # JPG TO DO SECURITY

    club = get_object_or_404(Organisation, pk=club_id)
    batch = get_object_or_404(BatchID, pk=batch_id_id)

    first_name_search = request.POST.get("member-search-first", "")
    last_name_search = request.POST.get("member-search-last", "")
    system_number_search = request.POST.get("member-search-number", "")

    members = []

    # if there is nothing to search for, don't search
    if not first_name_search and not last_name_search and not system_number_search:
        return HttpResponse("")

    member_list = MemberMembershipType.objects.filter(
        membership_type__organisation=club
    ).values_list("system_number", flat=True)

    users = User.objects.filter(system_number__in=member_list)
    un_regs = UnregisteredUser.objects.filter(system_number__in=member_list)

    # Subquery of MemberClubEmail filtering by system_number from UnregisteredUser
    un_reg_emails = MemberClubEmail.objects.filter(
        system_number=OuterRef("system_number")
    ).values("email")[:1]

    if first_name_search:

        users = users.filter(first_name__istartswith=first_name_search)

        un_regs = un_regs.filter(first_name__istartswith=first_name_search).annotate(
            email=Subquery(un_reg_emails)
        )

    elif last_name_search:

        users = users.filter(last_name__istartswith=last_name_search)

        un_regs = un_regs.filter(last_name__istartswith=last_name_search).annotate(
            email=Subquery(un_reg_emails)
        )

    else:
        # system number search

        users = users.annotate(
            system_number_string=Cast("system_number", CharField())
        ).filter(system_number_string__startswith=system_number_search)

        un_regs = (
            un_regs.annotate(system_number_string=Cast("system_number", CharField()))
            .filter(system_number_string__startswith=system_number_search)
            .annotate(email=Subquery(un_reg_emails))
        )

    members = list(chain(users, un_regs))

    return render(
        request,
        "notifications/batch_email_recipients_member_search_htmx.html",
        {
            "club": club,
            "batch": batch,
            "members": members,
        },
    )


def compose_email_recipients_add_tag(request, club_id, batch_id_id, tag_id):
    """Add recipients from a club tag"""

    # JPG TO DO SECURITY
    club = get_object_or_404(Organisation, pk=club_id)
    batch = get_object_or_404(BatchID, pk=batch_id_id)

    added_count = 0
    if tag_id == EVERYONE_TAG_ID:
        #  add all members

        all_members = MemberMembershipType.objects.filter(
            membership_type__organisation=club
        )
        for mmt in all_members:
            added, _ = _add_to_recipient_with_system_number(
                batch, club, mmt.system_number
            )
            added_count += added

    else:
        # add from a real club tag

        tag = get_object_or_404(ClubTag, pk=tag_id)
        tag_members = MemberClubTag.objects.filter(club_tag=tag)
        for mct in tag_members:
            added, _ = _add_to_recipient_with_system_number(
                batch, club, mct.system_number
            )
            added_count += added

    messages.add_message(
        request,
        messages.INFO,
        f"{added_count} recipient{'s' if added_count != 1 else ''} added",
    )

    return redirect("notifications:compose_email_recipients", club_id, batch_id_id)


def compose_email_recipients_add_member(request, club_id, batch_id_id, system_number):
    """Add a club member by system number as a recipient"""

    # JPG TO DO SECURITY
    club = get_object_or_404(Organisation, pk=club_id)
    batch = get_object_or_404(BatchID, pk=batch_id_id)

    added, feedback = _add_to_recipient_with_system_number(batch, club, system_number)

    messages.add_message(request, messages.INFO, feedback)

    return redirect("notifications:compose_email_recipients", club_id, batch_id_id)


def compose_email_recipients_remove_tag(
    request, club_id, batch_id_id, tag_id, from_all
):
    """Remove tagged club members from a batch's recipients
    Either from all recipeinets, or from added (ie not initial) recipients only"""

    # JPG TO DO SECURITY
    club = get_object_or_404(Organisation, pk=club_id)
    batch = get_object_or_404(BatchID, pk=batch_id_id)

    if tag_id == EVERYONE_TAG_ID:
        source = MemberMembershipType.objects.filter(membership_type__organisation=club)

    else:
        tag = get_object_or_404(ClubTag, pk=tag_id)
        source = MemberClubTag.objects.filter(club_tag=tag)

    system_numbers = [item.system_number for item in source.all()]

    if from_all:
        # un-include all occurances

        Recipient.objects.filter(
            batch=batch, system_number__in=system_numbers, include=True
        ).update(include=False)

    else:
        # only un-include from non-initial recipients

        Recipient.objects.filter(
            batch=batch, system_number__in=system_numbers, include=True, initial=False
        ).update(include=False)

    messages.add_message(
        request,
        messages.INFO,
        f"{'EVERYONE' if tag_id == EVERYONE_TAG_ID else tag.tag_name} removed",
    )

    return redirect("notifications:compose_email_recipients", club_id, batch_id_id)


@login_required()
def compose_email_options(request, club_id, batch_id_id):
    """Compose batch emails - step 2 - email options"""

    # JPG TO DO SECURITY
    club = get_object_or_404(Organisation, pk=club_id)
    batch = get_object_or_404(BatchID, pk=batch_id_id)

    if request.method == "POST":

        email_options_form = EmailOptionsForm(request.POST, club=club)

        if email_options_form.is_valid():

            # When a template is selected it populates the other two fields
            # from the template. These values can be changed and would then override
            # the template values. Rather than implement complex logic to determine
            # whether the values are being overridden, just save the values as provided.

            print("Doing post logic")

            if email_options_form.cleaned_data.get("template"):
                selected_template_id = email_options_form.cleaned_data.get("template")
                if selected_template_id != 0:
                    template = get_object_or_404(
                        OrgEmailTemplate, pk=selected_template_id
                    )
                else:
                    template = None
            else:
                template = None
                selected_template_id = None
            batch.template = template
            batch.reply_to = email_options_form.cleaned_data.get("reply_to")
            batch.from_name = email_options_form.cleaned_data.get("from_name")
            batch.save()

            print(
                f"Saved template id {batch.template.id}, reply_to '{batch.reply_to}', from_name '{batch.from_name}'"
            )

            #  proceed to step 3 - content
            return redirect("notifications:compose_email_content", club_id, batch_id_id)

    else:
        email_options_form = EmailOptionsForm(club=club)

        if batch.template:
            # use the stored template, but override the template value for the other two fields
            selected_template_id = batch.template.id
            email_options_form.fields["from_name"].initial = batch.from_name
            email_options_form.fields["reply_to"].initial = batch.reply_to
        elif len(email_options_form.fields["template"].choices) > 0:
            # first time through an templates exist so use the first and set the other fields accordingly
            selected_template_id = email_options_form.fields["template"].choices[0][0]
            template = get_object_or_404(OrgEmailTemplate, pk=selected_template_id)
            email_options_form.fields["from_name"].initial = template.from_name
            email_options_form.fields["reply_to"].initial = template.reply_to
        else:
            # no templates so just use defaults
            selected_template_id = None
            email_options_form.fields["from_name"].initial = batch.from_name
            email_options_form.fields["reply_to"].initial = batch.reply_to

    return render(
        request,
        "notifications/batch_email_options.html",
        {
            "seleceted_template_id": selected_template_id,
            "step": 2,
            "batch": batch,
            "club": club,
            "email_options_form": email_options_form,
        },
    )


def compose_email_options_from_and_reply_to_htmx(request, club_id, batch_id_id):
    """Rebuild the from and reply_to fields in the send email form if the template changes"""

    print("*** compose_email_options_from_and_reply_to_htmx ***")

    # JPG TO DO SECURITY
    club = get_object_or_404(Organisation, pk=club_id)
    batch = get_object_or_404(BatchID, pk=batch_id_id)

    template_id = request.POST.get("template")
    template = get_object_or_404(OrgEmailTemplate, pk=template_id)

    email_options_form = EmailOptionsForm(club=club)

    email_options_form.fields["from_name"].initial = template.from_name
    email_options_form.fields["reply_to"].initial = template.reply_to

    return render(
        request,
        "notifications/batch_email_options_from_and_reply_to_htmx.html",
        {"batch": batch, "club": club, "email_options_form": email_options_form},
    )


@login_required()
def compose_email_content(request, club_id, batch_id_id):
    """Compose batch emails - step 1 - review recipients"""

    # JPG TO DO SECURITY
    club = get_object_or_404(Organisation, pk=club_id)
    batch = get_object_or_404(BatchID, pk=batch_id_id)
    ready_to_send = False

    if request.method == "POST":

        email_content_form = EmailContentForm(request.POST)

        if email_content_form.is_valid():

            # TO DO post logic

            if hasattr(batch, "batchcontent"):
                batch.batchcontent.email_body = email_content_form.cleaned_data.get(
                    "email_body", ""
                )
                batch.batchcontent.save()
            else:
                new_content = BatchContent()
                new_content.batch = batch
                new_content.email_body = email_content_form.cleaned_data.get(
                    "email_body", ""
                )
                new_content.save()

            if email_content_form.cleaned_data.get("subject"):
                batch.description = email_content_form.cleaned_data.get(
                    "subject", "Batch email"
                )
                batch.save()

            ready_to_send = True
            pass

    else:

        email_content_form = EmailContentForm()
        email_content_form.fields["subject"].initial = batch.description

        if hasattr(batch, "batchcontent"):
            email_content_form.fields[
                "email_body"
            ].initial = batch.batchcontent.email_body
            ready_to_send = True

    return render(
        request,
        "notifications/batch_email_content.html",
        {
            "step": 3,
            "batch": batch,
            "club": club,
            "email_content_form": email_content_form,
            "ready_to_send": ready_to_send,
        },
    )


def compose_email_content_send_htmx(request, club_id, batch_id_id):
    """Handle sending a test message or the full batch

    Redirects to one of the process steps if there is an issue, otherwise
    redirects to the watch email view.
    """

    # JPG TO DO SECURITY
    club = get_object_or_404(Organisation, pk=club_id)
    batch = get_object_or_404(BatchID, pk=batch_id_id)

    (ok_to_send, error_message, rectification_step) = _validate_batch_details(
        batch_id_id
    )

    if ok_to_send:
        (attachments, attachment_size) = _attachment_dict_for_batch(batch)

        if attachment_size > 10_000_000:
            (ok_to_send, error_message, rectification_step) = (
                False,
                "Attachments are too large",
                3,
            )

    if ok_to_send:

        dispatched = _dispatch_batch(
            request,
            club,
            batch,
            attachments,
            test_user=request.user if "test" in request.POST else None,
        )

        if dispatched:
            if "test" in request.POST:
                messages.success(
                    request,
                    f"Test message sent to {request.user.email}",
                    extra_tags="cobalt-message-success",
                )

                return HttpResponse(f"Test message sent to {request.user.email}")
            else:
                # redirect to email watch view
                # is this really useful for very samll batches (eg 1-4 recipients)

                response = HttpResponse("Redirecting...", status=302)
                response["HX-Redirect"] = reverse(
                    "notifications:watch_emails", kwargs={"batch_id": batch.batch_id}
                )
                return response
        else:
            (ok_to_send, error_message, rectification_step) = (
                False,
                "Unable to send",
                3,
            )

    response = HttpResponse("Redirecting...", status=302)

    if rectification_step == 1:
        response["HX-Redirect"] = reverse(
            "notifications:compose_email_recipients",
            kwargs={"club_id": club_id, "batch_id": batch_id_id},
        )
    elif rectification_step == 2:
        response["HX-Redirect"] = reverse(
            "notifications:compose_email_options",
            kwargs={"club_id": club_id, "batch_id": batch_id_id},
        )
    else:
        response["HX-Redirect"] = reverse(
            "notifications:compose_email_content",
            kwargs={"club_id": club_id, "batch_id": batch_id_id},
        )

    messages.error(
        response,
        error_message,
        extra_tags="cobalt-message-error",
    )

    return response


def _attachment_dict_for_batch(batch):
    """Returns an attachment dictionary and total attachment size (bytes)"""

    attachment_ids = BatchAttachment.objects.filter(batch=batch).values_list(
        "attachment_id", flat=True
    )
    attachment_id_list = list(attachment_ids)
    attachments = {}
    total_size = 0.0
    if len(attachment_id_list) > 0:
        attachments_objects = EmailAttachment.objects.filter(id__in=attachment_id_list)
        for attachments_object in attachments_objects:
            mime_type, _ = mimetypes.guess_type(attachments_object.filename())
            if mime_type is None:
                attachments[
                    attachments_object.filename()
                ] = attachments_object.attachment.path
            else:
                attachments[attachments_object.filename()] = {
                    "file": attachments_object.attachment.path,
                    "mimetype": mime_type,
                }
            total_size += attachments_object.attachment.size
    return (attachments, total_size)


def _validate_batch_details(batch_id_id):
    """Check whether the batch is really ready to send

    Returns a tuple of:
        Success (Trie/False)
        User error message
        Process step to rectify (1,2, 3)
    """

    try:
        batch = BatchID.objects.get(pk=batch_id_id)
    except BatchID.DoesNotExist:
        return (False, "Batch does not exist")

    if batch.state != BatchID.BATCH_STATE_WIP:
        return (False, "Batch has already been sent")

    if len(batch.description) == 0:
        return (False, "Please specify a subject")

    recipient_count = Recipient.objects.filter(batch=batch, include=True).count()

    if recipient_count == 0:
        return (False, "Batch has no recipients")

    return (True, None, None)


def _dispatch_batch(request, club, batch, attachments, test_user=None):
    """Queue a batch of emails to be sent

    If a test_user is specified the email is only sent to that user.

    Returns success (true/false)
    """

    # get the recipients
    if test_user:
        recipients = [test_user]
    else:
        recipients = Recipient.objects.filter(
            batch=batch,
            include=True,
        )

    # build the template rendering context
    context = {
        "subject": batch.description,
    }

    if hasattr(batch, "batchcontent"):
        context["email_body"] = batch.batchcontent.email_body

    if batch.template:
        org_template = batch.template
    else:
        org_template = OrgEmailTemplate(organisation=club)

    print(f"*** org template = {org_template}")

    context["img_src"] = org_template.banner.url
    context["footer"] = org_template.footer
    context["box_colour"] = org_template.box_colour

    # determine which EmailTemplate to use, and update context with
    # and template specific parameters

    if batch.batch_type in [
        BatchID.BATCH_TYPE_CONGRESS,
        BatchID.BATCH_TYPE_EVENT,
    ]:

        po_template = "system - two headings"
        activity = BatchActivity.objects.filter(batch=batch).first()
        if activity.activity_type == BatchActivity.ACTIVITY_TYPE_CONGRESS:
            congress = get_object_or_404(Congress, pk=activity.activity_id)
        else:
            event = get_object_or_404(Event, pk=activity.activity_id)
            congress = event.congress
        context[
            "title1"
        ] = f"Message from {request.user.full_name} on behalf of {congress}"
        context["title2"] = batch.description

    elif batch.batch_type in [
        BatchID.BATCH_TYPE_MULTI,
    ]:

        po_template = "system - two headings"
        context["title1"] = f"Message from {request.user.full_name} on behalf of {club}"
        context["title2"] = batch.description

    elif batch.batch_type in [
        BatchID.BATCH_TYPE_COMMS,
        BatchID.BATCH_TYPE_RESULTS,
    ]:

        po_template = "system - club"
        context["title"] = batch.description
        context["box_font_colour"] = org_template.box_font_colour
    else:

        context["title"] = batch.description
        po_template = "system - default"

    print(f"*** po template = {po_template}")

    # other arguements required to send the email

    # from_name = batch.from_name  # where is this used ?
    reply_to = batch.reply_to

    if len(recipients) == 1:

        context["name"] = recipients[0].first_name

        send_cobalt_email_with_template(
            to_address=recipients[0].email,
            context=context,
            template=po_template,
            batch_id=batch,
            reply_to=reply_to,
            attachments=attachments if len(attachments) > 0 else None,
            batch_size=1,
        )

        if test_user is None:
            _finalise_email_batch(batch, batch_size=1)

    else:
        # send in a separate thread

        # start thread
        thread = Thread(
            target=_dispatch_batch_thread,
            args=[
                batch,
                recipients,
                context,
                po_template,
                reply_to,
                attachments,
            ],
        )
        thread.setDaemon(True)
        thread.start()

    return True


def _dispatch_batch_thread(
    batch,
    recipients,
    context,
    po_template,
    reply_to,
    attachments,
):
    """Asynchronous thread to send bulk emails for a batch"""

    # Mark the batch as in flight
    batch.state = BatchID.BATCH_STATE_IN_FLIGHT
    batch.batch_size = len(recipients)
    batch.save()

    for recipient in recipients:

        context["name"] = recipient.first_name

        send_cobalt_email_with_template(
            to_address=recipient.email,
            context=context,
            template=po_template,
            batch_id=batch,
            reply_to=reply_to,
            attachments=attachments if len(attachments) > 0 else None,
            batch_size=batch.batch_size,
        )

        logger.info(
            f"Queued email to {recipient.first_name} {recipient.first_name}, {recipient.email}"
        )

    _finalise_email_batch(batch)


@check_club_menu_access(check_comms=True)
def compose_email_content_attachment_htmx(request, club):
    """Handle the attachments pane"""

    batch_id_id = request.POST.get("batch_id_id")
    batch = get_object_or_404(BatchID, pk=batch_id_id)

    email_attachments = EmailAttachment.objects.filter(organisation=club).order_by(
        "-pk"
    )[:50]

    # Add hx_vars for the delete function
    for email_attachment in email_attachments:
        email_attachment.hx_vars = (
            f"club_id:{club.id},email_attachment_id:{email_attachment.id}"
        )
        email_attachment.modal_id = f"del_attachment{email_attachment.id}"

    return render(
        request,
        "notifications//batch_email_content_email_attachment_htmx.html",
        {"club": club, "batch": batch, "email_attachments": email_attachments},
    )

    return HttpResponse("Work in progress")


@check_club_menu_access(check_comms=True)
def compose_email_content_upload_new_email_attachment_htmx(request, club):
    """Upload a new email attachment for a club
    Use the HTMX hx-trigger response header to tell the browser about it
    """

    # JPG TO DO SECURITY

    batch_id_id = request.POST.get("batch_id_id")
    batch = get_object_or_404(BatchID, pk=batch_id_id)

    form = EmailAttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        email_attachment = form.save(commit=False)
        email_attachment.organisation = club
        email_attachment.save()

        trigger = f"""{{"post_attachment_add":{{"id": "{email_attachment.id}" , "name": "{email_attachment.filename()}"}}}}"""

        return _email_attachment_list_htmx(
            request, club, batch, hx_trigger_response=trigger
        )

    return HttpResponse("Error")


def _email_attachment_list_htmx(request, club, batch, hx_trigger_response=None):
    """Shows just the list of attachments, called if we delete or add an attachment"""

    email_attachments = EmailAttachment.objects.filter(organisation=club).order_by(
        "-pk"
    )[:50]

    # Add hx_vars for the delete function
    for email_attachment in email_attachments:
        email_attachment.hx_vars = (
            f"club_id:{club.id},email_attachment_id:{email_attachment.id}"
        )
        email_attachment.modal_id = f"del_attachment{email_attachment.id}"

    # For delete we need to trigger a response in the browser to remove this from the list (if present)
    # We use the hx_trigger response header for this

    response = render(
        request,
        "notifications/batch_email_content_email_attachments_list_htmx.html",
        {"club": club, "batch": batch, "email_attachments": email_attachments},
    )

    if hx_trigger_response:
        response["HX-Trigger"] = hx_trigger_response

    return response


@check_club_menu_access(check_comms=True)
def compose_email_content_include_attachment_htmx(request, club):
    """Include an attachment in the email

    Needs to be called with hx-vars for club_id, batch_id_id, attachement_id

    Save to the model and return the list of included attachments"""

    print(
        f"*** compose_email_content_include_attachment_htmx att_id: {request.POST.get('attachment_id')}"
    )

    # JPG TO DO SECURITY

    batch_id_id = request.POST.get("batch_id_id")
    batch = get_object_or_404(BatchID, pk=batch_id_id)

    attachment_id = request.POST.get("attachment_id")
    attachment = get_object_or_404(EmailAttachment, pk=attachment_id)

    existing = BatchAttachment.objects.filter(
        batch=batch, attachment=attachment
    ).first()

    if not existing:
        print(f"*** adding attachment {attachment} to batch {batch}")
        batch_attachment = BatchAttachment()
        batch_attachment.batch = batch
        batch_attachment.attachment = attachment
        batch_attachment.save()
        print(f"*** ADDED batch attachment {batch_attachment}")

    return _compose_email_content_included_attachments_htmx(request, club, batch)


@check_club_menu_access(check_comms=True)
def compose_email_content_remove_attachment_htmx(request, club):
    """Remove a batch attachment from the email

    Needs to be called with hx-vars for club_id, batch_id_id and batch_attachment_id

    Update the model and return the list of included attachments"""

    # JPG TO DO SECURITY

    batch_id_id = request.POST.get("batch_id_id")
    batch = get_object_or_404(BatchID, pk=batch_id_id)

    batch_attachment_id = request.POST.get("batch_attachment_id")
    batch_attachment = get_object_or_404(BatchAttachment, pk=batch_attachment_id)

    batch_attachment.delete()

    return _compose_email_content_included_attachments_htmx(request, club, batch)


@check_club_menu_access(check_comms=True)
def compose_email_content_included_attachments_htmx(request, club):
    """Return the list of included attachments (ie batch attachments)

    Request must specify the batch_id_id
    """

    print("*** compose_email_content_included_attachments_htmx")

    # JPG TO DO SECURITY

    batch_id_id = request.POST.get("batch_id_id")
    batch = get_object_or_404(BatchID, pk=batch_id_id)

    return _compose_email_content_included_attachments_htmx(request, club, batch)


def _compose_email_content_included_attachments_htmx(request, club, batch):
    """Return the list of included attachments (ie batch attachments)"""

    print(f"   >>> _compose_email_content_included_attachments_htmx batch={batch}")

    batch_attachments = BatchAttachment.objects.filter(batch=batch)

    print(f"   >>> {len(batch_attachments)} batch attachments found ")

    return render(
        request,
        "notifications/batch_email_content_included_attachments_htmx.html",
        {
            "batch": batch,
            "club": club,
            "batch_attachments": batch_attachments,
        },
    )


def _finalise_email_batch(batch, batch_size=None):
    """Clean-up processing once a batch has been sent"""

    if batch_size is not None:
        batch.batch_size = batch_size

    batch.state = BatchID.BATCH_STATE_COMPLETE
    batch.save()

    if hasattr(batch, "batchcontent"):
        BatchContent.objects.filter(batch=batch).delete()

    Recipient.objects.filter(batch=batch).delete()

    BatchAttachment.objects.filter(batch=batch).delete()


def delete_email_batch(request, batch_id_id):
    """Delete an incomplete batch"""

    # JPG TO DO SECURITY

    batch = get_object_or_404(BatchID, pk=batch_id_id)
    batch.delete()

    return redirect(
        "organisations:club_menu_tab_entry_point", batch.organisation.id, "comms"
    )
