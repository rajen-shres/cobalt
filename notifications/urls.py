# pylint: disable=missing-module-docstring,missing-class-docstring
from django.urls import path

import notifications.notifications_views.admin
import notifications.notifications_views.core
from django_ses.views import SESEventWebhookView

app_name = "notifications"  # pylint: disable=invalid-name

urlpatterns = [
    path(
        "ses/event-webhook/",
        SESEventWebhookView.as_view(),
        name="handle-event-webhook",
    ),
    path("", notifications.notifications_views.user.homepage, name="homepage"),
    path(
        "passthrough/<int:id>/",
        notifications.notifications_views.user.passthrough,
        name="passthrough",
    ),
    path(
        "deleteall",
        notifications.notifications_views.user.delete_all_in_app_notifications,
        name="deleteall",
    ),
    path(
        "delete/<int:id>/",
        notifications.notifications_views.user.delete_in_app_notification,
        name="delete",
    ),
    path(
        "admin/email/view-all",
        notifications.notifications_views.admin.admin_view_all_emails,
        name="admin_view_all",
    ),
    path(
        "admin/email/view-email/<int:email_id>",
        notifications.notifications_views.admin.admin_view_email,
        name="admin_view_email",
    ),
    path(
        "admin/email/view-email-by-batch/<int:batch_id>",
        notifications.notifications_views.admin.admin_view_email_by_batch,
        name="admin_view_email_by_batch",
    ),
    path(
        "admin/email/view-email-send-copy/<int:email_id>",
        notifications.notifications_views.admin.admin_send_email_copy_to_admin,
        name="admin_send_email_copy_to_admin",
    ),
    path(
        "admin/realtime/view",
        notifications.notifications_views.admin.admin_view_realtime_notifications,
        name="admin_view_realtime_notifications",
    ),
    path(
        "admin/realtime/view-details/<int:header_id>",
        notifications.notifications_views.admin.admin_view_realtime_notification_detail,
        name="admin_view_realtime_notification_detail",
    ),
    path(
        "admin/realtime/view-item/<int:notification_id>",
        notifications.notifications_views.admin.admin_view_realtime_notification_item,
        name="admin_view_realtime_notification_item",
    ),
    path(
        "admin/realtime/global-view",
        notifications.notifications_views.admin.global_admin_view_realtime_notifications,
        name="global_admin_view_realtime_notifications",
    ),
    path(
        "admin/email/view-email",
        notifications.notifications_views.admin.admin_view_email,
        name="admin_view_email",
    ),
    path(
        "email/send-email/<int:member_id>",
        notifications.notifications_views.core.email_contact,
        name="email_contact",
    ),
    path(
        "email/watch_emails/<str:batch_id>",
        notifications.notifications_views.user.watch_emails,
        name="watch_emails",
    ),
    path(
        "system-admin/player-view/<int:member_id>",
        notifications.notifications_views.admin.global_admin_view_emails,
        name="global_admin_view_emails",
    ),
    path(
        "mobile-device/send-test/<int:fcm_device_id>",
        notifications.notifications_views.core.send_test_fcm_message,
        name="send_test_fcm_message",
    ),
]
