from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse

from forums.models import Forum, Post
from notifications.models import InAppNotification, Email, NotificationMapping
from utils.utils import cobalt_paginator


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

    return note_count, notifications


def acknowledge_in_app_notification(id):
    note = InAppNotification.objects.get(id=id)
    note.acknowledged = True
    note.save()
    return note


@login_required
def homepage(request):
    """homepage for notifications listings"""

    notes = InAppNotification.objects.filter(member=request.user).order_by(
        "-created_date"
    )
    things = cobalt_paginator(request, notes, 10)
    return render(request, "notifications/homepage.html", {"things": things})


@login_required()
def watch_emails(request, batch_id):
    """Track progress of email by batch id"""

    emails = Email.objects.filter(batch_id=batch_id)
    emails_queued = emails.filter(status="Queued").count()
    emails_sent = emails.filter(status="Sent").count()

    sender = emails[0].sender

    # Don't show link to details if too many for page
    show_details = emails.count() < 5000

    return render(
        request,
        "notifications/watch_email.html",
        {
            "emails_queued": emails_queued,
            "emails_sent": emails_sent,
            "batch_id": batch_id,
            "sender": sender,
            "show_details": show_details,
        },
    )


@login_required
def delete_in_app_notification(request, id):
    """when a user clicks on delete we come here. returns the homepage"""
    notification = InAppNotification.objects.filter(pk=id, member=request.user).first()
    if notification:
        notification.delete()
    return homepage(request)


@login_required
def delete_all_in_app_notifications(request):
    """when a user clicks on delete all we come here. returns the homepage"""
    InAppNotification.objects.filter(member=request.user).delete()
    return homepage(request)


@login_required
def passthrough(request, id):
    """passthrough function to acknowledge a message has been clicked on"""

    note = acknowledge_in_app_notification(id)
    return redirect(note.link)


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


def notifications_status_summary():
    """Used by utils status to get a status of notifications"""

    latest = Email.objects.all().order_by("-id").first()
    pending = Email.objects.filter(status="Queued").count()

    last_hour_date_time = datetime.now() - timedelta(hours=1)

    last_hour = Email.objects.filter(created_date__gt=last_hour_date_time).count()

    return {"latest": latest, "pending": pending, "last_hour": last_hour}
