from django.urls import path
from . import views, helpdesk

app_name = "support"  # pylint: disable=invalid-name

urlpatterns = [
    path("", views.home, name="support"),
    path("admin-faq", views.admin, name="admin"),
    path("browser-errors", views.browser_errors, name="browser_errors"),
    path("search", views.search, name="search"),
    path("cookies", views.cookies, name="cookies"),
    path("contact", views.contact, name="contact"),
    path("guidelines", views.guidelines, name="guidelines"),
    path("acceptable-use", views.acceptable_use, name="acceptable_use"),
    path(
        "non-production-email-changer",
        views.non_production_email_changer,
        name="non_production_email_changer",
    ),
    path("helpdesk-create", helpdesk.create_ticket, name="create_ticket"),
    path("helpdesk-menu", helpdesk.helpdesk_menu, name="helpdesk_menu"),
    path("helpdesk-list", helpdesk.helpdesk_list, name="helpdesk_list"),
    path("helpdesk-list/<int:ticket_id>", helpdesk.edit_ticket, name="helpdesk_edit"),
]
