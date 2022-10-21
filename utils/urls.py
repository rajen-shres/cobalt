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
    path(
        "admin-show-aws-infrastructure-info",
        views.admin_show_aws_infrastructure_info,
        name="admin_show_aws_infrastructure_info",
    ),
    path(
        "admin-show-aws-infrastructure-app-version",
        views.admin_show_aws_app_version_htmx,
        name="admin_show_aws_app_version_htmx",
    ),
    path(
        "admin-show-database-details",
        views.admin_show_database_details_htmx,
        name="admin_show_database_details_htmx",
    ),
    path(
        "admin-system-activity",
        views.admin_system_activity,
        name="admin_system_activity",
    ),
]
