from django.urls import path
from . import views

app_name = "utils"  # pylint: disable=invalid-name

urlpatterns = [
    path("geo-location/<str:location>", views.geo_location, name="geo_location"),
    path("batch", views.batch, name="batch"),
    path("user-activity", views.user_activity, name="user_activity"),
    path("status", views.status, name="status"),
    path("database", views.database_view, name="database_view"),
    path("recent-errors", views.recent_errors, name="recent_errors"),
    path("get-facts-text", views.get_facts_text, name="get_facts_text"),
]
