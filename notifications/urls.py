# pylint: disable=missing-module-docstring,missing-class-docstring
from django.urls import path
from . import views
from django_ses.views import SESEventWebhookView
from django.views.decorators.csrf import csrf_exempt

app_name = "notifications"  # pylint: disable=invalid-name

urlpatterns = [
    path(
        "ses/event-webhook/",
        SESEventWebhookView.as_view(),
        name="handle-event-webhook",
    ),
    path("", views.homepage, name="homepage"),
    path("passthrough/<int:id>/", views.passthrough, name="passthrough"),
    path("deleteall", views.deleteall, name="deleteall"),
    path("delete/<int:id>/", views.delete, name="delete"),
    path("admin/email/view-all", views.admin_view_all_emails, name="admin_view_all"),
    path(
        "admin/email/view-email/<int:email_id>",
        views.admin_view_email,
        name="admin_view_email",
    ),
    path(
        "admin/email/view-email-by-batch/<int:batch_id>",
        views.admin_view_email_by_batch,
        name="admin_view_email_by_batch",
    ),
    path(
        "admin/email/view-email-send-copy/<int:email_id>",
        views.admin_send_email_copy_to_admin,
        name="admin_send_email_copy_to_admin",
    ),
    path("admin/email/view-email", views.admin_view_email, name="admin_view_email"),
    path("email/send-email/<int:member_id>", views.email_contact, name="email_contact"),
    path("email/watch_emails/<str:batch_id>", views.watch_emails, name="watch_emails"),
    path(
        "system-admin/player-view/<int:member_id>",
        views.global_admin_view_emails,
        name="global_admin_view_emails",
    ),
]
