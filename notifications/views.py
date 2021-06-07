""" Notifications handles messages that Cobalt applications wish to pass to users.

    See `Notifications Overview`_ for more details.

.. _Notifications Overview:
   ./notifications_overview.html

"""
from threading import Thread
from django.utils import timezone
import boto3
from accounts.models import User
from cobalt.settings import (
    ADMINS,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION_NAME,
    AWS_ACCESS_KEY_ID,
)
from cobalt.settings import (
    DEFAULT_FROM_EMAIL,
    GLOBAL_TITLE,
    TBA_PLAYER,
    RBAC_EVERYONE,
    COBALT_HOSTNAME,
)

from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMultiAlternatives
from django.db import connection, transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags
from forums.models import Forum, Post
from logs.views import log_event
from rbac.core import rbac_user_has_role

from datetime import datetime, timedelta
from django.contrib import messages
from django.utils.safestring import mark_safe
import time

from rbac.views import rbac_forbidden
from utils.utils import cobalt_paginator

from .forms import EmailContactForm
from .models import InAppNotification, NotificationMapping, Email, EmailThread
import random
import string

# Max no of emails to send in a batch
MAX_EMAILS = 2

# Max number of threads
MAX_EMAIL_THREADS = 1


class CobaltEmail:
    """ Class to handle sending emails. See the notifications_overview in the docs for an explanation """

    def __init__(self):
        """ initiate instance"""

        # Batch id is associated with this instance of CobaltEmail. All outgoing emails will get this batch_id
        self.batch_id = "%s-%s-%s" % (
            "".join(random.choices(string.ascii_uppercase + string.digits, k=4)),
            "".join(random.choices(string.ascii_uppercase + string.digits, k=4)),
            "".join(random.choices(string.ascii_uppercase + string.digits, k=4)),
        )

    def queue_email(self, to_address, subject, message, member=None, reply_to=""):
        """Adds email to the queue ready to send. Why no bcc_address? No need to bcc when sending to only one person.

        Args:
            to_address (str): who to send to
            subject (str): subject line for email
            message (str): message to send in HTML or plain format
            member (User): who this is being sent to (optional)
            reply_to (str): who to send replies to

        Returns:
            Nothing
        """
        Email(
            subject=subject,
            message=message,
            batch_id=self.batch_id,
            recipient=to_address,
            member=member,
            reply_to=reply_to,
        ).save()

    def empty_queue(self):
        """ Empty the queue if required. Must be done in real time or the batch process will send anyway. """

        Email.objects.filter(batch_id=self.batch_id).delete()

    def _post_commit(self):
        """ Called after the database commit has completed """

        # Create an email thread record to show we are running
        self.email_thread = EmailThread()
        self.email_thread.save()

        # start thread
        thread = Thread(target=self._send_queued_emails_thread)
        thread.setDaemon(True)
        thread.start()

    def send(self):
        """send queued emails if threading limit not reached yet
        We could avoid the database call and add the email objects
        to memory but we might run out of memory for a large email campaign
        """

        active_threads = EmailThread.objects.all().count()

        print("active threads %s" % active_threads)

        if active_threads >= MAX_EMAIL_THREADS:
            # Overloaded. Will need to wait for the cron job to run and pick this up
            log_event(
                user=None,
                severity="CRITICAL",
                source="Notifications",
                sub_source="Email",
                message="Cannot start email thread, too many already running: %s"
                % active_threads,
            )
            print(
                "Cannot start email thread, too many already running: %s"
                % active_threads
            )
            return

        # We need to wait for the database commit before we can start the thread
        transaction.on_commit(self._post_commit)

    def _send_queued_emails_thread(self):
        """ Send out queued emails. This thread does the actual work."""

        try:

            emails = Email.objects.filter(status="Queued").filter(
                batch_id=self.batch_id
            )

            for email in emails:
                plain_message = strip_tags(email.message)

                # check for none
                if email.reply_to is None:
                    email.reply_to = ""

                msg = EmailMultiAlternatives(
                    email.subject,
                    plain_message,
                    to=[email.recipient],
                    from_email=DEFAULT_FROM_EMAIL,
                    reply_to=[email.reply_to],
                )

                msg.attach_alternative(email.message, "text/html")

                msg.send()

                email.status = "Sent"
                email.sent_date = timezone.now()
                email.save()

                print(f"Sent email to {email.recipient}")

        finally:

            # Remove our thread from the list
            self.email_thread.delete()

            # Django creates a new database connection for this thread so close it
            connection.close()


def send_cobalt_email(to_address, subject, message, member=None, reply_to=""):
    """Send single email. This sets off an async task to actually send the
        email to avoid delays for the user. This should only be used for small
        numbers of emails, one being a good example.

    Args:
        to_address (str): who to send to
        subject (str): subject line for email
        message (str): message to send in HTML or plain format
        member (User): who this is being sent to (optional)
        reply_to (str): who to send replies to

    Returns:
        Nothing
    """

    # Add to queue
    email = Email(
        subject=subject,
        message=message,
        recipient=to_address,
        member=member,
        reply_to=reply_to,
    )
    email.save()

    # start thread
    thread = Thread(target=send_cobalt_email_thread, args=[email.id])
    thread.setDaemon(True)
    thread.start()


def send_cobalt_email_thread(email_id):
    """Send single email. Asynchronous thread

    Args:
        email_id (int): pk for email to send

    Returns:
        Nothing
    """

    # It is possible for this thread to start before the email has been
    # saved to the database. Not ideal, but a pause solves this
    time.sleep(2)

    email = Email.objects.get(pk=email_id)

    plain_message = strip_tags(email.message)

    message = EmailMultiAlternatives(
        email.subject,
        plain_message,
        to=[email.recipient],
        from_email=DEFAULT_FROM_EMAIL,
        reply_to=[email.reply_to],
    )

    message.attach_alternative(email.message, "text/html")

    message.send()

    email.status = "Sent"
    email.save()

    # Django creates a new database connection for this thread so close it
    connection.close()


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


def send_cobalt_sms(phone_number, msg):
    """Send single SMS

    Args:
        phone_number (str): who to send to
        msg (str): message to send

    Returns:
        Nothing
    """

    client = boto3.client(
        "sns",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION_NAME,
    )

    client.publish(
        PhoneNumber=phone_number,
        Message=msg,
        MessageAttributes={
            "AWS.SNS.SMS.SenderID": {"DataType": "String", "StringValue": GLOBAL_TITLE}
        },
    )


def get_notifications_for_user(user):
    """Get a list of all unacklowledged notifications for a user

    Returns a list of notifications for the user where the status is
    unacknowledged.

    If the list is over 10 then the last item is a link to the notifications
    page to view them all.

    Args:
        user (User): standard User object

    Returns:
        tuple: Count of notifications and List of notifications which themselves are tuples
    """

    notifications = []
    note_count = InAppNotification.objects.filter(
        member=user, acknowledged=False
    ).count()
    notes = InAppNotification.objects.filter(member=user, acknowledged=False).order_by(
        "-created_date"
    )[:10]

    for note in notes:
        notifications.append(
            (note.message, reverse("notifications:passthrough", kwargs={"id": note.id}))
        )
    if note_count > 0:
        notifications.append(
            ("---- Show all notifications ----", reverse("notifications:homepage"))
        )
    #
    return (note_count, notifications)


def contact_member(member, msg, contact_type, link=None, html_msg=None, subject=None):
    """ Contact member using email or SMS """

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
        send_cobalt_email(member.email, subject, html_msg, member)

    if contact_type == "SMS":
        send_cobalt_sms(member.mobile, msg)


def create_user_notification(
    member,
    application_name,
    event_type,
    topic,
    subtopic=None,
    notification_type="Email",
):
    """create a notification record for a user

    Used to programatically create a notification record. For example Forums
    will call this to register a notification for comments on a users post.

    Args:
        member(User): standard User object
        application_name(str): name of the Cobalt application to follow
        event_type(str): event e.g. forums.post.create
        topic(str): specific to the application. e.g. 5 to follow forum with pk=5
        subtopic(str): application specific (optional)
        notification_type(str): email or SMS

    Returns:
        Nothing
    """

    notification = NotificationMapping()
    notification.member = member
    notification.application = application_name
    notification.event_type = event_type
    notification.topic = topic
    notification.subtopic = subtopic
    notification.notification_type = notification_type
    notification.save()


def notify_happening_forums(
    application_name,
    event_type,
    msg,
    topic,
    subtopic=None,
    link=None,
    html_msg=None,
    email_subject=None,
    user=None,
):
    """sub function for notify_happening() - handles Forum events
    Might be able to make this generic
    """
    listeners = NotificationMapping.objects.filter(
        application=application_name,
        event_type=event_type,
        topic=topic,
        subtopic=subtopic,
    )

    for listener in listeners:
        if user != listener.member:
            # Add first name
            html_msg = html_msg.replace("[NAME]", listener.member.first_name)
            contact_member(
                listener.member,
                msg,
                listener.notification_type,
                link,
                html_msg,
                email_subject,
            )


def notify_happening(
    application_name,
    event_type,
    msg,
    topic,
    subtopic=None,
    link=None,
    html_msg=None,
    email_subject=None,
    user=None,
):
    """Called by Cobalt applications to tell notify they have done something.

    Main entry point for general notifications of events within the system.
    Applications publish an event through this call and Notifications tells
    any member who has registered an interest in this event.

    Args:
        application_name(str): name of the calling app
        event_type(str):
        topic(str): specific to the application, high level event
        subtopic(str): specific to the application, next level event
        msg(str): a brief description of the event
        link(str): an HTML relative link to the event (Optional)
        html_msg(str): a long description of the event (Optional)
        email_subject(str): subject line for email (Optional)

    Returns:
        Nothing

    """

    if application_name == "Forums":
        notify_happening_forums(
            application_name,
            event_type,
            msg,
            topic,
            subtopic,
            link,
            html_msg,
            email_subject,
            user,
        )


def add_in_app_notification(member, msg, link=None):
    note = InAppNotification()
    note.member = member
    note.message = msg[:100]
    note.link = link
    note.save()


def acknowledge_in_app_notification(id):
    note = InAppNotification.objects.get(id=id)
    note.acknowledged = True
    note.save()
    return note


def delete_in_app_notification(id):
    InAppNotification.objects.filter(id=id).delete()


def delete_all_in_app_notifications(member):
    InAppNotification.objects.filter(member=member).delete()


@login_required
def homepage(request):
    """ homepage for notifications listings """

    notes = InAppNotification.objects.filter(member=request.user).order_by(
        "-created_date"
    )
    things = cobalt_paginator(request, notes, 10)
    return render(request, "notifications/homepage.html", {"things": things})


@login_required
def delete(request, id):
    """ when a user clicks on delete we come here. returns the homepage """
    delete_in_app_notification(id)
    return homepage(request)


@login_required
def deleteall(request):
    """ when a user clicks on delete all we come here. returns the homepage """
    delete_all_in_app_notifications(request.user)
    return homepage(request)


def passthrough(request, id):
    """ passthrough function to acknowledge a message has been clicked on """

    note = acknowledge_in_app_notification(id)
    return redirect(note.link)


def add_listener(
    member,
    application,
    event_type,
    topic=None,
    subtopic=None,
    notification_type="Email",
):
    """ Add a user to be notified of an event """

    listener = NotificationMapping(
        member=member,
        application=application,
        event_type=event_type,
        topic=topic,
        subtopic=subtopic,
        notification_type=notification_type,
    )
    listener.save()


def remove_listener(member, application, event_type, topic=None, subtopic=None):
    """ Remove a user from being notified of an event """

    listeners = NotificationMapping.objects.filter(
        member=member,
        application=application,
        event_type=event_type,
        topic=topic,
        subtopic=subtopic,
    )
    for listener in listeners:
        listener.delete()


def check_listener(member, application, event_type, topic=None, subtopic=None):
    """ Check if a user is being notified of an event """

    listeners = NotificationMapping.objects.filter(
        member=member,
        application=application,
        event_type=event_type,
        topic=topic,
        subtopic=subtopic,
    )
    if listeners:
        return True
    else:
        return False


def notifications_in_english(member):
    """returns a list of notifications in a simple English format.
    This is hand coded and needs to be updated when new notifications are
    defined. Used by Accounts:Settings but can be used more generally."""

    notifications = NotificationMapping.objects.filter(member=member)
    for notification in notifications:
        if notification.application == "Forums":
            if notification.event_type == "forums.post.create":
                forum = Forum.objects.filter(pk=notification.topic).first()
                notification.description = f"New posts in '{forum.title}'"
                notification.type = "Posts"
            if notification.event_type == "forums.post.comment":
                post = Post.objects.filter(pk=notification.topic).first()
                notification.description = (
                    f"Comments on '{post.title}' in Forum: {post.forum}"
                )
                notification.type = "Comments"

    return notifications


@login_required()
def admin_view_all(request):
    """ Show email notifications for administrators """

    # check access
    role = "notifications.admin.view"
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    emails = Email.objects.all().order_by("-pk")
    things = cobalt_paginator(request, emails)

    return render(request, "notifications/admin_view_all.html", {"things": things})


@login_required()
def admin_view_email(request, email_id):
    """ Show single email for administrators """

    # check access
    role = "notifications.admin.view"
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    email = get_object_or_404(Email, pk=email_id)

    return render(request, "notifications/admin_view_email.html", {"email": email})


def notifications_status_summary():
    """ Used by utils status to get a status of notifications """

    latest = Email.objects.all().order_by("-id").first()
    pending = Email.objects.filter(status="Queued").count()

    last_hour_date_time = datetime.now() - timedelta(hours=1)

    last_hour = Email.objects.filter(created_date__gt=last_hour_date_time).count()

    return {"latest": latest, "pending": pending, "last_hour": last_hour}


@login_required()
def email_contact(request, member_id):
    """ email contact form """

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
            "host": COBALT_HOSTNAME,
        }

        html_msg = render_to_string("notifications/email.html", context)

        send_cobalt_email(
            to_address=member.email,
            subject=title,
            message=html_msg,
            member=member,
            reply_to=f"{request.user.email}",
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


@login_required()
def resend_email_to_contact(request, email_id):
    """ Re-send single email that is in queued status """

    # check access
    role = "notifications.admin.view"
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    email = get_object_or_404(Email, pk=email_id)

    plain_message = strip_tags(email.message)

    # send_mail(
    #     email.subject,
    #     plain_message,
    #     DEFAULT_FROM_EMAIL,
    #     [email.recipient],
    #     html_message=email.message,
    # )

    message = EmailMultiAlternatives(
        email.subject,
        plain_message,
        to=[email.recipient],
        from_email=DEFAULT_FROM_EMAIL,
    )

    message.attach_alternative(email.message, "text/html")

    message.send()

    email.status = "Sent"
    email.save()
    messages.success(request, "Email scheduled to resent")
    return redirect("notifications:admin_view_all")


@login_required()
def resend_all_queued_emails(request):
    """ Send all emails that are in "Queued" status """
    # check access
    role = "notifications.admin.view"
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    queued_emails = Email.objects.filter(status="Queued")
    message = ""
    for email in queued_emails:
        plain_message = strip_tags(email.message)

        # send_mail(
        #     email.subject,
        #     plain_message,
        #     DEFAULT_FROM_EMAIL,
        #     [email.recipient],
        #     html_message=email.message,
        # )

        message = EmailMultiAlternatives(
            email.subject,
            plain_message,
            to=[email.recipient],
            from_email=DEFAULT_FROM_EMAIL,
        )

        message.attach_alternative(email.message, "text/html")

        message.send()

        email.status = "Sent"
        email.save()
        message += f"Resending email to {email.recipient} <br/>"
    messages.success(request, mark_safe(message))
    return redirect("notifications:admin_view_all")
