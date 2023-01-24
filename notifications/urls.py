# pylint: disable=missing-module-docstring,missing-class-docstring
from django.urls import path

import notifications.views.admin
import notifications.views.aws
import notifications.views.core
import notifications.views.user
from django_ses.views import SESEventWebhookView

import notifications.views.redirect

app_name = "notifications"  # pylint: disable=invalid-name

urlpatterns = [
    path(
        "ses/event-webhook/",
        SESEventWebhookView.as_view(),
        name="handle-event-webhook",
    ),
    path("", notifications.views.user.homepage, name="homepage"),
    path(
        "passthrough/<int:id>/",
        notifications.views.user.passthrough,
        name="passthrough",
    ),
    path(
        "deleteall",
        notifications.views.user.delete_all_in_app_notifications,
        name="deleteall",
    ),
    path(
        "delete/<int:id>/",
        notifications.views.user.delete_in_app_notification,
        name="delete",
    ),
    path(
        "admin/email/view-all",
        notifications.views.admin.admin_view_all_emails,
        name="admin_view_all",
    ),
    path(
        "admin/email/view-email/<int:email_id>",
        notifications.views.admin.admin_view_email,
        name="admin_view_email",
    ),
    path(
        "admin/email/view-email-by-batch/<int:batch_id>",
        notifications.views.admin.admin_view_email_by_batch,
        name="admin_view_email_by_batch",
    ),
    path(
        "admin/email/view-email-send-copy/<int:email_id>",
        notifications.views.admin.admin_send_email_copy_to_admin,
        name="admin_send_email_copy_to_admin",
    ),
    path(
        "admin/realtime/view",
        notifications.views.admin.admin_view_realtime_notifications,
        name="admin_view_realtime_notifications",
    ),
    path(
        "admin/realtime/view-details/<int:header_id>",
        notifications.views.admin.admin_view_realtime_notification_detail,
        name="admin_view_realtime_notification_detail",
    ),
    path(
        "admin/realtime/view-item/<int:notification_id>",
        notifications.views.admin.admin_view_realtime_notification_item,
        name="admin_view_realtime_notification_item",
    ),
    path(
        "admin/realtime/global-view",
        notifications.views.admin.global_admin_view_realtime_notifications,
        name="global_admin_view_realtime_notifications",
    ),
    path(
        "admin/email/view-email",
        notifications.views.admin.admin_view_email,
        name="admin_view_email",
    ),
    path(
        "email/send-email/<int:member_id>",
        notifications.views.core.email_contact,
        name="email_contact",
    ),
    path(
        "email/watch_emails/<str:batch_id>",
        notifications.views.user.watch_emails,
        name="watch_emails",
    ),
    path(
        "system-admin/player-view/<int:member_id>",
        notifications.views.admin.global_admin_view_emails,
        name="global_admin_view_emails",
    ),
    path(
        "system-admin/global-admin-view-real-time-for-user/<int:member_id>",
        notifications.views.admin.global_admin_view_real_time_for_user,
        name="global_admin_view_real_time_for_user",
    ),
    path(
        "mobile-device/send-test/<int:fcm_device_id>",
        notifications.views.core.send_test_fcm_message,
        name="send_test_fcm_message",
    ),
    path(
        "click/<str:message_id>/<str:redirect_path>",
        notifications.views.redirect.email_click_handler,
        name="email_click_handler",
    ),
    path(
        "admin-aws-suppression",
        notifications.views.aws.admin_aws_suppression,
        name="admin_aws_suppression",
    ),
    path(
        "member-to-member-email/<int:member_id>",
        notifications.views.user.member_to_member_email,
        name="member_to_member_email",
    ),
    path(
        "member-to-member-reply-to-email/<str:batch_id>",
        notifications.views.user.member_to_member_email_reply,
        name="member_to_member_email_reply",
    ),
    path(
        "admin-send-test-fcm-message",
        notifications.views.admin.admin_send_test_fcm_message,
        name="admin_send_test_fcm_message",
    ),
]
