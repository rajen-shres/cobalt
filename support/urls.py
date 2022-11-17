from django.urls import path
from . import views, helpdesk

app_name = "support"  # pylint: disable=invalid-name

urlpatterns = [
    path("", views.home, name="support"),
    path("admin-faq", views.admin, name="admin"),
    path("browser-errors", views.browser_errors, name="browser_errors"),
    path("search", views.global_search, name="search"),
    path("cookies", views.cookies, name="cookies"),
    path("contact-logged-in", views.contact_logged_in, name="contact_logged_in"),
    path("contact-logged-out", views.contact_logged_out, name="contact_logged_out"),
    path("guidelines", views.guidelines, name="guidelines"),
    path("acceptable-use", views.acceptable_use, name="acceptable_use"),
    path(
        "non-production-email-changer",
        views.non_production_email_changer,
        name="non_production_email_changer",
    ),
    path("helpdesk/create", helpdesk.create_ticket, name="create_ticket"),
    path("helpdesk/menu", helpdesk.helpdesk_menu, name="helpdesk_menu"),
    path("helpdesk/list", helpdesk.helpdesk_list, name="helpdesk_list"),
    path(
        "helpdesk/admin/add-notify",
        helpdesk.helpdesk_admin_add_notify,
        name="helpdesk_admin_notify",
    ),
    path(
        "helpdesk/admin/add-staff",
        helpdesk.helpdesk_admin_add_staff,
        name="helpdesk_admin_add_staff",
    ),
    path("helpdesk/admin", helpdesk.helpdesk_admin, name="helpdesk_admin"),
    path("helpdesk/edit/<int:ticket_id>", helpdesk.edit_ticket, name="helpdesk_edit"),
    path(
        "helpdesk/add-comment/<int:ticket_id>",
        helpdesk.add_comment,
        name="helpdesk_add_comment",
    ),
    path("helpdesk/user-list", helpdesk.user_list_tickets, name="helpdesk_user_list"),
    path(
        "helpdesk/user-edit/<int:ticket_id>",
        helpdesk.user_edit_ticket,
        name="helpdesk_user_edit",
    ),
    path(
        "helpdesk/attachments/<int:ticket_id>",
        helpdesk.helpdesk_attachments,
        name="helpdesk_attachments",
    ),
    path(
        "helpdesk-ajax-delete-attachment",
        helpdesk.helpdesk_delete_attachment_ajax,
        name="helpdesk_delete_attachment_ajax",
    ),
    path(
        "helpdesk-ajax-delete-notify",
        helpdesk.helpdesk_delete_notify_ajax,
        name="helpdesk_delete_notify_ajax",
    ),
    path(
        "helpdesk-ajax-delete-staff",
        helpdesk.helpdesk_delete_staff_ajax,
        name="helpdesk_delete_staff_ajax",
    ),
]
