from django.urls import path

import utils.views.cobalt_batch
import utils.views.general
import utils.views.monitoring
import utils.views.slugs

app_name = "utils"  # pylint: disable=invalid-name

urlpatterns = [
    path(
        "geo-location/<str:location>",
        utils.views.general.geo_location,
        name="geo_location",
    ),
    path("batch", utils.views.cobalt_batch.batch, name="batch"),
    path("user-activity", utils.views.monitoring.user_activity, name="user_activity"),
    path("status", utils.views.monitoring.system_status, name="status"),
    path("statistics", utils.views.monitoring.system_statistics, name="statistics"),
    path("database", utils.views.monitoring.database_view, name="database_view"),
    path("recent-errors", utils.views.monitoring.recent_errors, name="recent_errors"),
    path(
        "admin-show-aws-infrastructure-info",
        utils.views.monitoring.admin_show_aws_infrastructure_info,
        name="admin_show_aws_infrastructure_info",
    ),
    path(
        "admin-show-aws-infrastructure-app-version",
        utils.views.monitoring.admin_show_aws_app_version_htmx,
        name="admin_show_aws_app_version_htmx",
    ),
    path(
        "admin-show-database-details",
        utils.views.monitoring.admin_show_database_details_htmx,
        name="admin_show_database_details_htmx",
    ),
    path(
        "admin-system-activity",
        utils.views.monitoring.admin_system_activity,
        name="admin_system_activity",
    ),
    path(
        "admin-system-activity-nginx",
        utils.views.monitoring.admin_system_activity_nginx_htmx,
        name="admin_system_activity_nginx_htmx",
    ),
    path(
        "admin-system-activity-cobalt-messages",
        utils.views.monitoring.admin_system_activity_cobalt_messages_htmx,
        name="admin_system_activity_cobalt_messages_htmx",
    ),
    path(
        "admin-system-activity-users",
        utils.views.monitoring.admin_system_activity_users_htmx,
        name="admin_system_activity_users_htmx",
    ),
    path(
        "admin-system-settings",
        utils.views.monitoring.admin_system_settings,
        name="admin_system_settings",
    ),
    path(
        "get-aws-environment-status",
        utils.views.monitoring.get_aws_environment_status_htmx,
        name="get_aws_environment_status_htmx",
    ),
    path(
        "api-log-viewer",
        utils.views.general.api_log_viewer,
        name="api_log_viewer",
    ),
    path(
        "admin-manage-slugs",
        utils.views.slugs.admin_manage_slugs,
        name="admin_manage_slugs",
    ),
    # path(
    #     "timeout",
    #     utils.views.general.timeout,
    #     name="timeout",
    # ),
]
