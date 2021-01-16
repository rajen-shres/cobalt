from django.urls import path
from . import views

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
]
