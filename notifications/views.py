""" Notifications handles messages that Cobalt applications wish to pass to users.

    See `Notifications Overview`_ for more details.

.. _Notifications Overview:
   ./notifications_overview.html

"""
import boto3
from cobalt.settings import AWS_SECRET_ACCESS_KEY, AWS_REGION_NAME, AWS_ACCESS_KEY_ID
from .models import InAppNotification, NotificationMapping, Email
from .forms import EmailContactForm
from forums.models import Forum, Post
from accounts.models import User

# from django.core.mail import send_mail
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags
from django.utils import timezone
from cobalt.settings import (
    DEFAULT_FROM_EMAIL,
    GLOBAL_TITLE,
    TBA_PLAYER,
    RBAC_EVERYONE,
    COBALT_HOSTNAME,
)
from django.template.loader import render_to_string
from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from utils.utils import cobalt_paginator
from threading import Thread
from django.db import connection
from rbac.views import rbac_forbidden
from rbac.core import rbac_user_has_role
from datetime import datetime, timedelta
from django.contrib import messages
import time


def send_cobalt_email(to_address, subject, message, member=None, reply_to=""):
    """Send single email. This sets off an async task to actually send the
        email to avoid delays for the user.

    Args:
        to_address (str): who to send to
        subject (str): subject line for email
        msg (str): message to send in HTML or plain format
        member (User): who this is being sent to (optional)

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
        reply_to=[email.reply_to],
    )

    message.attach_alternative(email.message, "text/html")

    message.send()

    email.status = "Sent"
    email.save()

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

        return redirect("dashboard:dashboard")

    return render(
        request, "notifications/email_form.html", {"form": form, "member": member}
    )
