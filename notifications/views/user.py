from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils.safestring import mark_safe

from accounts.models import User
from forums.models import Forum, Post
from notifications.forms import MemberToMemberEmailForm
from notifications.models import (
    InAppNotification,
    NotificationMapping,
    Snooper,
    BatchID,
    EmailBatchRBAC,
)
from notifications.views.core import (
    send_cobalt_email_with_template,
    create_rbac_batch_id,
)
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
    note = get_object_or_404(InAppNotification, pk=id)
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
    """
    Track progress of email by batch id
    """

    batch_id_object = get_object_or_404(BatchID, batch_id=batch_id)

    # COB-793 change to notify user of limited notifications
    # emails = Snooper.objects.filter(batch_id=batch_id_object)
    emails = Snooper.objects.select_related("post_office_email").filter(
        batch_id=batch_id_object
    )

    large_batch = emails.first().limited_notifications if emails.first() else False
    if large_batch:

        # use sent count from post_office rather than snoopers
        # and assume all emails are either =sent or queued
        emails_sent = emails.filter(post_office_email__status=0).count()
        emails_queued = emails.count() - emails_sent

    else:

        emails_queued = emails.filter(ses_sent_at=None).count()
        emails_sent = emails.exclude(ses_sent_at=None).count()

    return render(
        request,
        "notifications/watch_email.html",
        {
            "emails_queued": emails_queued,
            "emails_sent": emails_sent,
            "batch_id": batch_id,
            "large_batch": large_batch,
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


def _send_member_to_member_email(request, member):
    """send a member to member email or a reply"""

    subject = request.POST["subject"]
    message = request.POST["message"].replace("\n", "<br>")
    msg = f"""
               Email from: {request.user}<br><br>
               <b>{subject}</b>
               <br><br>
               {message}
     """

    # Create a batch id, to obscure sender on edit link. User is sender.
    batch_id = create_rbac_batch_id(
        "notifications.member_comms.view", user=request.user
    )

    link = reverse(
        "notifications:member_to_member_email_reply", kwargs={"batch_id": batch_id}
    )

    context = {
        "link": link,
        "link_text": "reply",
        "name": member.first_name,
        "title": f"Email from: {request.user.full_name}",
        "subject": subject,
        "email_body": mark_safe(msg),
    }

    send_cobalt_email_with_template(
        to_address=member.email,
        batch_id=batch_id,
        context=context,
    )

    messages.success(
        request,
        "Email queued successfully",
        extra_tags="cobalt-message-success",
    )

    redirect_to = request.POST.get("redirect_to", "dashboard:dashboard")
    return redirect(redirect_to)


@login_required()
def member_to_member_email(request, member_id):
    """Allow one member to email another"""

    # TODO: Add in app notification

    member = get_object_or_404(User, pk=member_id)

    form = MemberToMemberEmailForm(request.POST or None)

    if request.method == "POST":
        return _send_member_to_member_email(request, member)

    return render(
        request,
        "notifications/member_to_member_email.html",
        {
            "form": form,
            "member": member,
        },
    )


@login_required()
def member_to_member_email_reply(request, batch_id):
    """Allow one member to reply via email to another"""

    # TODO: Add in app notification

    # Get the batch from the batch id
    batch_thing = BatchID.objects.filter(batch_id=batch_id).latest("pk")
    batch = EmailBatchRBAC.objects.filter(batch_id=batch_thing).latest("pk")
    post_office_email = (
        Snooper.objects.filter(batch_id=batch.batch_id).first().post_office_email
    )

    # get the sender from the batch
    member = batch.meta_sender

    form = MemberToMemberEmailForm(request.POST or None)

    if request.method == "POST":
        return _send_member_to_member_email(request, member)

    form.initial["message"] = f"<br><hr> {post_office_email.context['email_body']}"

    subject = post_office_email.context["subject"]
    if subject.find("RE: ") != 0:
        subject = f"RE: {subject}"

    form.initial["subject"] = subject

    return render(
        request,
        "notifications/member_to_member_email_reply.html",
        {
            "form": form,
            "member": member,
        },
    )
