import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils.safestring import SafeString
from post_office import mail as po_email
from post_office.models import Email as PostOfficeEmail

from accounts.models import User
from cobalt.settings import DEFAULT_FROM_EMAIL, GLOBAL_TITLE
from masterpoints.views import user_summary
from notifications.models import (
    EmailBatchRBAC,
    Snooper,
    RealtimeNotificationHeader,
    RealtimeNotification,
)
from notifications.notifications_views.core import _cloudwatch_reader
from rbac.core import rbac_user_has_role
from rbac.decorators import rbac_check_role
from rbac.views import rbac_forbidden
from utils.utils import cobalt_paginator


@login_required()
def admin_view_all_emails(request):
    """Show email notifications for administrators"""

    # check access
    role = "notifications.admin.view"
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    emails = PostOfficeEmail.objects.all().select_related("snooper").order_by("-pk")
    things = cobalt_paginator(request, emails)

    return render(
        request, "notifications/admin_view_all_emails.html", {"things": things}
    )


@login_required()
def admin_view_email_by_batch(request, batch_id):
    """Show an email from a batch"""

    batch = get_object_or_404(EmailBatchRBAC, pk=batch_id)

    admin_role = "notifications.admin.view"

    if not (
        rbac_user_has_role(request.user, batch.rbac_role)
        or rbac_user_has_role(request.user, admin_role)
    ):
        return rbac_forbidden(request, batch.rbac_role)

    snoopers = Snooper.objects.filter(batch_id=batch_id)

    if not snoopers:
        return HttpResponse("Not found")

    return render(
        request,
        "notifications/admin_view_email.html",
        {"email": snoopers.first().post_office_email, "snoopers": snoopers},
    )


@login_required()
def admin_view_email(request, email_id):
    """Show single email for administrators"""

    email = get_object_or_404(PostOfficeEmail, pk=email_id)

    # check access
    snooper = (
        Snooper.objects.select_related("batch_id")
        .filter(post_office_email=email)
        .first()
    )

    admin_role = "notifications.admin.view"

    try:
        rbac_role = (
            EmailBatchRBAC.objects.filter(batch_id=snooper.batch_id).first().rbac_role
        )
    except AttributeError:
        rbac_role = admin_role

    if not (
        rbac_user_has_role(request.user, rbac_role)
        or rbac_user_has_role(request.user, admin_role)
    ):
        return rbac_forbidden(request, rbac_role)

    return render(request, "notifications/admin_view_email.html", {"email": email})


@login_required()
def admin_send_email_copy_to_admin(request, email_id):
    """Send a copy of an email to an admin so they can see it fully rendered

    With using templates for Django post office emails and render_on_delivery,
    we no longer have a copy of the email. We can regenerate it though by
    sending to someone else.

    """

    # check access
    role = "notifications.admin.view"
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    email = get_object_or_404(PostOfficeEmail, pk=email_id)

    # DEFAULT_FROM_EMAIL could be 'a@b.com' or 'something something<a@b.com>'
    if DEFAULT_FROM_EMAIL.find("<") >= 0:
        parts = DEFAULT_FROM_EMAIL.split("<")
        from_name = f"Email Copy from {GLOBAL_TITLE}<{parts[1]}"
    else:
        from_name = f"Email Copy from {GLOBAL_TITLE}<{DEFAULT_FROM_EMAIL}>"

    po_email.send(
        request.user.email,
        from_name,
        template=email.template,
        context=email.context,
        render_on_delivery=True,
        priority="now",
    )

    return HttpResponse("Message sent. Check your inbox.")


@rbac_check_role("notifications.realtime_send.edit")
def admin_view_realtime_notifications(request):
    """Allow an admin to see their notifications

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """
    notification_headers = RealtimeNotificationHeader.objects.filter(
        admin=request.user
    ).order_by("-pk")
    things = cobalt_paginator(request, notification_headers)

    return render(request, "notifications/admin_view_realtime.html", {"things": things})


@rbac_check_role("notifications.admin.view")
def global_admin_view_realtime_notifications(request):
    """Allow a global admin to see all real time notifications

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """
    notification_headers = RealtimeNotificationHeader.objects.order_by("-pk")
    things = cobalt_paginator(request, notification_headers)

    return render(request, "notifications/admin_view_realtime.html", {"things": things})


@rbac_check_role("notifications.realtime_send.edit", "notifications.admin.view")
def admin_view_realtime_notification_detail(request, header_id):
    """Show the detail of a batch of messages. Actually allows anyone with
       notifications.realtime_send.edit to see any batch, but that is okay.

    Args:
        request (HTTPRequest): standard request object
        header_id (int): id of the RealtimeNotificationHeader to show

    Returns:
        HTTPResponse
    """
    notification_header = get_object_or_404(RealtimeNotificationHeader, pk=header_id)

    # Convert string to json
    notification_header.uncontactable_users = (
        notification_header.get_uncontactable_users()
    )
    notification_header.unregistered_users = (
        notification_header.get_unregistered_users()
    )
    notification_header.invalid_lines = notification_header.get_invalid_lines()

    notifications = RealtimeNotification.objects.filter(
        header=notification_header
    ).select_related("member")

    return render(
        request,
        "notifications/admin_view_realtime_detail.html",
        {"notification_header": notification_header, "notifications": notifications},
    )


@rbac_check_role("notifications.realtime_send.edit", "notifications.admin.view")
def admin_view_realtime_notification_item(request, notification_id):
    """Show the detail of a single message. Actually allows anyone with
       notifications.realtime_send.edit to see the message, but that is okay.
       We save the AWS Message Id when we send the message, this looks in the
       AWS Cloudwatch logs to find out what happened subsequently.

    Args:
        request (HTTPRequest): standard request object
        notification_id (int): id of the RealtimeNotification to show

    Returns:
        HTTPResponse
    """
    notification = get_object_or_404(RealtimeNotification, pk=notification_id)

    # TODO: Move this to a global variable
    success_log_group = "sns/ap-southeast-2/730536189139/DirectPublishToPhoneNumber"
    error_log_group = (
        "sns/ap-southeast-2/730536189139/DirectPublishToPhoneNumber/Failure"
    )

    success_results = _cloudwatch_reader(success_log_group, notification)

    if success_results:
        results = success_results
        successful = True
    else:  # Try for errors, format is the same
        results = _cloudwatch_reader(error_log_group, notification)
        successful = False

    if results:
        message = results[0]["message"]
        message_json = json.loads(message)
        delivery = message_json["delivery"]
        cloudwatch = SafeString(f"<pre>{json.dumps(delivery, indent=4)}</pre>")
        provider_response = delivery["providerResponse"]
    else:
        cloudwatch = "No data found"
        provider_response = "No data found"

    raw_cloudwatch = SafeString(f"<pre>{json.dumps(results, indent=4)}</pre>")

    return render(
        request,
        "notifications/admin_view_realtime_item.html",
        {
            "notification": notification,
            "provider_response": provider_response,
            "cloudwatch": cloudwatch,
            "raw_cloudwatch": raw_cloudwatch,
            "successful": successful,
        },
    )


@rbac_check_role("notifications.admin.view")
def global_admin_view_emails(request, member_id):
    """Allow an admin to see emails for a player

    Args:
        member_id: member to look up
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    member = get_object_or_404(User, pk=member_id)
    summary = user_summary(member.system_number)

    email_list = PostOfficeEmail.objects.filter(to=[member.email]).order_by("-pk")[:50]

    return render(
        request,
        "notifications/global_admin_view_emails.html",
        {
            "profile": member,
            "summary": summary,
            "emails": email_list,
        },
    )
