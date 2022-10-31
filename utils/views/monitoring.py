import datetime
import os
import re
import subprocess

import boto3
import pytz
from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.db import connection, ProgrammingError
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe

from accounts.models import User
from accounts.views.core import get_user_statistics
from cobalt.settings import (
    COBALT_HOSTNAME,
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION_NAME,
    TIME_ZONE,
)
from events.views.core import events_status_summary, get_event_statistics
from forums.views import forums_status_summary, get_forum_statistics
from logs.views import get_logs_statistics
from notifications.views.admin import notifications_status_summary
from notifications.views.core import get_notifications_statistics
from organisations.views.general import get_org_statistics
from payments.views.core import payments_status_summary, get_payments_statistics
from rbac.decorators import rbac_check_role
from rbac.views import get_rbac_statistics
from results.views.core import get_results_statistics
from support.helpdesk import get_support_statistics
from utils.forms import SystemSettingsForm
from utils.utils import cobalt_paginator

from importlib import import_module

# from importlib import import_module


def _get_aws_environment():
    """Get the environment object if we can. There is no way to have AWS credentials with access only
    to specific environments (e.g. cobalt-test-black), you either have the access to change things or
    you don't. We do some hard coding to get around this.

    Returns:
        status: True or False - whether we succeeded or not
        aws_environment_name - string with environment name or failure message
        settings - dict of settings

    """

    # Dictionary of hostname to environment prefix
    environment_map = {
        "myabf.com.au": "cobalt-production",
        "uat.myabf.com.au": "cobalt-uat",
        "test.myabf.com.au": "cobalt-test",
        "127.0.0.1:8000": "cobalt-test",
    }

    environment_prefix = environment_map.get(COBALT_HOSTNAME)
    if not environment_prefix:
        return False, "Error - environment not found", "", {}

    # Create AWS client
    eb_client = boto3.client(
        "elasticbeanstalk",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION_NAME,
    )

    # Get environments
    environments = eb_client.describe_environments(
        ApplicationName="cobalt",
    )["Environments"]

    # find the AWS name for this environment, check for duplicates, and get the variables
    aws_environment_name = None
    for environment in environments:
        if environment["EnvironmentName"].find(environment_prefix) >= 0:
            if aws_environment_name:
                return False, "Error - duplicate environments found", {}
            aws_environment_name = environment["EnvironmentName"]

    if not aws_environment_name:
        return False, "No environment found", "", {}

    # Now get the sessions for the environment
    settings = eb_client.describe_configuration_settings(
        ApplicationName="cobalt", EnvironmentName=aws_environment_name
    )

    # Just get the environment variables, ignore the rest
    settings_dict = {}

    for setting in settings["ConfigurationSettings"][0]["OptionSettings"]:
        if setting["Namespace"] == "aws:elasticbeanstalk:application:environment":
            settings_dict[setting["OptionName"]] = setting["Value"]

    return True, aws_environment_name, environment_prefix, settings_dict


@login_required
def user_activity(request):
    """show user activity figures"""

    users = (
        User.objects.order_by("-last_activity")
        .exclude(last_activity=None)
        .exclude(id=request.user.id)
    )

    five_min_ago = timezone.now() - datetime.timedelta(minutes=5)
    last_5m = User.objects.filter(last_activity__gte=five_min_ago).count()

    one_hour_ago = timezone.now() - datetime.timedelta(hours=1)
    last_1hr = User.objects.filter(last_activity__gte=one_hour_ago).count()

    one_day_ago = timezone.now() - datetime.timedelta(days=1)
    last_day = User.objects.filter(last_activity__gte=one_day_ago).count()

    one_week_ago = timezone.now() - datetime.timedelta(days=7)
    last_week = User.objects.filter(last_activity__gte=one_week_ago).count()

    one_month_ago = timezone.now() - datetime.timedelta(days=30)
    last_month = User.objects.filter(last_activity__gte=one_month_ago).count()

    things = cobalt_paginator(request, users)

    return render(
        request,
        "utils/monitoring/user_activity.html",
        {
            "things": things,
            "last_5m": last_5m,
            "last_1hr": last_1hr,
            "last_day": last_day,
            "last_week": last_week,
            "last_month": last_month,
        },
    )


@login_required()
def database_view(request):
    """Show basic stats about the database"""

    db_sizes = []

    with connection.cursor() as cursor:

        for app in apps.get_app_configs():
            for app_model in app.get_models():
                name = app_model.__name__.lower()
                try:
                    # Pretty printed disk space
                    cursor.execute(
                        f"SELECT pg_size_pretty(pg_total_relation_size('{app.verbose_name.lower()}_{name}'));"
                    )
                    ans = cursor.fetchall()
                    pretty = ans[0][0]

                    # Disk space in bytes
                    cursor.execute(
                        f"SELECT pg_total_relation_size('{app.verbose_name.lower()}_{name}');"
                    )
                    ans = cursor.fetchall()

                    # Count of rows
                    local_array = {}
                    exec_cmd = (
                        "module = import_module('%s.models')\ncount = module.%s.objects.count()"
                        % (app.verbose_name.lower(), app_model.__name__)
                    )
                    exec(exec_cmd, globals(), local_array)

                    # Add it all to dictionary
                    db_sizes.append(
                        {
                            "name": f"{app.verbose_name}: {app_model.__name__}",
                            "size": ans[0][0],
                            "pretty": pretty,
                            "count": local_array["count"],
                        }
                    )

                except (ProgrammingError, ModuleNotFoundError):
                    # We get some noise through, just ignore it
                    pass

    total_size = 0
    total_rows = 0
    for db_size in db_sizes:
        total_size += db_size["size"]
        total_rows += db_size["count"]

    return render(
        request,
        "utils/monitoring/database_view.html",
        {"db_sizes": db_sizes, "total_size": total_size, "total_rows": total_rows},
    )


@login_required()
def admin_show_aws_infrastructure_info(request):
    """Show some AWS info to check on health of system"""

    # TODO: Security - RBAC Role

    # Create AWS client
    eb_client = boto3.client(
        "elasticbeanstalk",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION_NAME,
    )

    # Get environments
    environments = eb_client.describe_environments(
        ApplicationName="cobalt",
    )["Environments"]

    # Go through environments and get the EC2 instances
    for environment in environments:
        instance_health = eb_client.describe_instances_health(
            EnvironmentName=environment["EnvironmentName"], AttributeNames=["All"]
        )["InstanceHealthList"]

        environment["instance_health"] = instance_health

    return render(
        request,
        "utils/monitoring/admin_show_aws_infrastructure_info.html",
        {"environments": environments},
    )


@login_required()
def get_aws_environment_status_htmx(request):
    """Shows the status of the environment. Called by admin_system_settings after we make a change. Quite specific to
    the function it serves."""

    environment = request.POST.get("environment")

    eb_client = boto3.client(
        "elasticbeanstalk",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION_NAME,
    )

    status = eb_client.describe_environments(
        ApplicationName="cobalt",
        EnvironmentNames=[environment],
    )["Environments"][0]["Status"]

    if status == "Ready":
        # Return special HTTP Response Code to tell HTMX to stop polling
        return HttpResponse("<div><h2>System Ready!</h2></div>", status=286)

    # Show status and spinner
    return HttpResponse(
        f"""<div class="row pb-5">
                                <div class="col-4">
                                    <span class="loader"></span>
                                </div>
                                <div class="col-8">
                                    <h1>{status}...</h1>
                                </div>
                            </div> """
    )


@login_required()
def admin_show_aws_app_version_htmx(request):
    """Show the Elastic Beanstalk App details for a version"""

    app_id = request.POST.get("app_id")

    # Create AWS client
    eb_client = boto3.client(
        "elasticbeanstalk",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION_NAME,
    )

    try:

        response = eb_client.describe_application_versions(
            ApplicationName="cobalt",
            VersionLabels=[
                app_id,
            ],
        )

    except Exception as exp:
        return HttpResponse(exp.__str__())

    # We will get only one thing in the list
    return HttpResponse(response["ApplicationVersions"][0]["Description"])


@login_required()
def admin_show_database_details_htmx(request):
    """Show the database info for an environment"""

    # Environment will be something like cobalt-production-green, DB name will be cobalt-production
    environment_name = request.POST.get("environment")

    db_name = "-".join(environment_name.split("-")[:-1])

    # boto clients
    rds_client = boto3.client(
        "rds",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION_NAME,
    )

    cloudwatch_client = boto3.client(
        "cloudwatch",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION_NAME,
    )

    # Get details about the database
    db_details = rds_client.describe_db_instances(DBInstanceIdentifier=db_name)[
        "DBInstances"
    ][0]

    # Get CPU from Cloudwatch
    expression = f"""SELECT AVG(DBLoadCPU)
                        FROM SCHEMA("AWS/RDS", DBInstanceIdentifier)
                        WHERE DBInstanceIdentifier = '{db_name}'"""

    response = cloudwatch_client.get_metric_data(
        MetricDataQueries=[
            {
                "Id": "av_cpu",
                "Expression": expression,
                "Period": 300,
            },
        ],
        StartTime=timezone.now() - datetime.timedelta(minutes=5),
        EndTime=timezone.now(),
    )

    try:
        cpu = 100 * response["MetricDataResults"][0]["Values"][0]
    except TypeError:
        cpu = "Unavailable"

    return render(
        request,
        "utils/monitoring/admin_show_database_details_htmx.html",
        {"db_details": db_details, "cpu": cpu},
    )


@login_required()
def admin_system_activity(request):
    """Show basic info about user activity"""

    return render(request, "utils/monitoring/admin_system_activity.html")


@login_required()
def admin_system_activity_nginx_htmx(request):
    """Provide latest data from the nginx access.log"""

    # Regex for nginx access.log taken from Stack Overflow.
    conf = '$remote_addr - $remote_user [$time_local] "$type $request" $status $body_bytes_sent "$http_referer" "$http_user_agent"'
    regex = "".join(
        "(?P<" + g + ">.*?)" if g else re.escape(c)
        for g, c in re.findall(r"\$(\w+)|(.)", conf)
    )

    # Use a script to tail the log for us
    proc = subprocess.Popen(["utils/local/tail_nginx_log.sh"], stdout=subprocess.PIPE)
    lines = proc.stdout.readlines()
    lines.reverse()

    log_data = []

    # Go through and see if we can better format the data
    for line in lines:

        line = line.decode("utf-8").strip()
        data = re.match(regex, line)
        if data:
            ngix_values = data.groupdict()

            # date
            date_string = ngix_values["time_local"]
            event_date = datetime.datetime.strptime(date_string, "%d/%b/%Y:%H:%M:%S %z")
            ngix_values["time_local"] = event_date

            # Status code
            status_code = int(ngix_values["status"])
            if 200 <= status_code < 300:
                ngix_values["status_icon"] = mark_safe(
                    "<span class='text-success'>check_circle</span>"
                )
            elif 300 <= status_code < 400:
                ngix_values["status_icon"] = "done"
            elif 400 <= status_code < 500:
                ngix_values["status_icon"] = "help"
            elif 500 <= status_code < 600:
                ngix_values["status_icon"] = "error"

            # request - remove HTTP part
            ngix_values["request"] = ngix_values["request"].replace("HTTP/1.1", "")

            log_data.append(ngix_values)

    return render(
        request,
        "utils/monitoring/admin_system_activity_nginx_htmx.html",
        {"log_data": log_data},
    )


@login_required()
def admin_system_activity_cobalt_messages_htmx(request):
    """Provide latest data from the cobalt messages log"""

    # Regex for log adapted from Stack Overflow.
    conf = "[$severity] $log_date $log_time [$file $func $line] $message"
    regex = "".join(
        f"(?P<{g}>.*?)" if g else re.escape(c)
        for g, c in re.findall(r"\$(\w+)|(.)", conf)
    )

    # Use a script to tail the log for us
    proc = subprocess.Popen(
        ["utils/local/tail_cobalt_messages_log.sh"], stdout=subprocess.PIPE
    )
    lines = proc.stdout.readlines()
    lines.reverse()

    log_data = []

    # Go through and see if we can better format the data
    for line in lines:

        line = line.decode("utf-8").strip()
        data = re.match(regex, line)
        if data:
            log_values = data.groupdict()

            # message doesn't come through properly
            message = line.split("]")[2]
            log_values["message"] = message

            # fix date (already in local time)
            date_string = f"{log_values['log_date']} {log_values['log_time']}"
            log_values["time_local"] = datetime.datetime.strptime(
                date_string, "%Y-%m-%d %H:%M:%S"
            )

            log_data.append(log_values)

    return render(
        request,
        "utils/monitoring/admin_system_activity_cobalt_messages_htmx.html",
        {"log_data": log_data},
    )


@login_required()
def admin_system_activity_users_htmx(request):
    """Provide latest data from user activity"""

    last_activity = (
        User.objects.all()
        .exclude(last_activity=None)
        .exclude(pk=request.user.pk)
        .order_by("-last_activity")[:30]
    )

    return render(
        request,
        "utils/monitoring/admin_system_activity_users_htmx.html",
        {"last_activity": last_activity},
    )


@rbac_check_role("system.admin.edit")
def admin_system_settings(request):
    """Manage system-wide settings"""

    message = ""
    update_made = False

    if request.POST:

        # Get aws name of this system and its settings
        (
            call_status,
            aws_environment_name,
            environment_type,
            settings,
        ) = _get_aws_environment()

        option_settings = [
            {
                "Namespace": "aws:elasticbeanstalk:application:environment",
                "OptionName": "DISABLE_PLAYPEN",
                "Value": request.POST.get("disable_playpen", "OFF").upper(),
            },
            {
                "Namespace": "aws:elasticbeanstalk:application:environment",
                "OptionName": "MAINTENANCE_MODE",
                "Value": request.POST.get("maintenance_mode", "OFF").upper(),
            },
            {
                "Namespace": "aws:elasticbeanstalk:application:environment",
                "OptionName": "DEBUG",
                "Value": request.POST.get("debug_flag", "OFF").upper(),
            },
        ]

        # Create AWS client
        eb_client = boto3.client(
            "elasticbeanstalk",
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION_NAME,
        )

        try:
            eb_client.update_environment(
                ApplicationName="cobalt",
                EnvironmentName=aws_environment_name,
                OptionSettings=option_settings,
            )
        except Exception as exc:
            return render(
                request,
                "utils/monitoring/admin_system_settings.html",
                {"message": exc.__str__()},
            )

        message = "Changes saved. This may take several minutes to be applied."

        update_made = True

    # Get aws name of this system and its settings
    (
        call_status,
        aws_environment_name,
        environment_type,
        settings,
    ) = _get_aws_environment()

    # Quit if we got an error
    if not call_status:
        return render(
            request,
            "utils/monitoring/admin_system_settings.html",
            {"message": aws_environment_name},
        )

    # Get the setting we are interested in
    debug_flag = settings.get("DEBUG") == "ON"
    disable_playpen = settings.get("DISABLE_PLAYPEN") == "ON"
    maintenance_mode = settings.get("MAINTENANCE_MODE") == "ON"

    initial = {
        "debug_flag": debug_flag,
        "disable_playpen": disable_playpen,
        "maintenance_mode": maintenance_mode,
    }

    form = SystemSettingsForm(initial=initial)

    return render(
        request,
        "utils/monitoring/admin_system_settings.html",
        {
            "message": message,
            "aws_environment_name": aws_environment_name,
            "environment_type": environment_type,
            "debug_flag": debug_flag,
            "disable_playpen": disable_playpen,
            "maintenance_mode": maintenance_mode,
            "form": form,
            "update_made": update_made,
        },
    )


@login_required()
def system_statistics(request):
    """Basic statistics"""

    user_statistics = get_user_statistics()
    event_statistics = get_event_statistics()
    payments_statistics = get_payments_statistics()
    notifications_statistics = get_notifications_statistics()
    forum_statistics = get_forum_statistics()
    org_statistics = get_org_statistics()
    rbac_statistics = get_rbac_statistics()
    support_statistics = get_support_statistics()
    logs_statistics = get_logs_statistics()
    results_statistics = get_results_statistics()

    return render(
        request,
        "utils/monitoring/system_statistics.html",
        {
            "user_statistics": user_statistics,
            "event_statistics": event_statistics,
            "payments_statistics": payments_statistics,
            "notifications_statistics": notifications_statistics,
            "forum_statistics": forum_statistics,
            "org_statistics": org_statistics,
            "rbac_statistics": rbac_statistics,
            "support_statistics": support_statistics,
            "logs_statistics": logs_statistics,
            "results_statistics": results_statistics,
        },
    )


@login_required()
def system_status(request):
    """Basic system health"""

    # if not rbac_user_has_role(request.user, "support.support.view"):
    #     return rbac_forbidden(request, "support.support.view")

    # Activity
    one_hour_ago = timezone.now() - datetime.timedelta(hours=1)

    users = (
        User.objects.order_by("-last_activity")
        .exclude(last_activity=None)
        .exclude(id=request.user.id)
        .filter(last_activity__gte=one_hour_ago)
        .count()
    )

    # Payments
    payments = payments_status_summary()

    # Emails
    notifications = notifications_status_summary()

    # Events
    events = events_status_summary()

    # Forums
    forums = forums_status_summary()

    # Get build time of this release
    TZ = pytz.timezone(TIME_ZONE)

    stat_time = os.stat("__init__.py").st_mtime
    utc_build_date = datetime.datetime.fromtimestamp(stat_time)
    build_date = TZ.localize(utc_build_date)

    return render(
        request,
        "utils/monitoring/system_status.html",
        {
            "users": users,
            "payments": payments,
            "notifications": notifications,
            "events": events,
            "forums": forums,
            "build_date": build_date,
        },
    )


@login_required()
def recent_errors(request):
    """Show recent errors from error log messages"""

    lines = (
        subprocess.run(["tail", "-1000", "/var/log/messages"], stdout=subprocess.PIPE)
        .stdout.decode("utf-8")
        .splitlines()
    )

    errors = []

    matches = [
        "systemd",
        "dhcpd",
        "dhclient",
        "rsyslogd",
        "ec2net",
        "[INFO]",
        "healthd",
        "journal:",
        "nginx",
        "favicon.ico",
    ]

    for line in lines:
        if all(match not in line for match in matches):
            parts = line.split(" ")
            timestamp = f"{parts[0]} {parts[1]} {parts[2]}"
            # We get some rubbish in the logs some times, find last occurence of web:
            loc = line.rfind("web:")
            # fmt: off
            message = line[loc + 5:]
            # fmt: on
            errors.append({"timestamp": timestamp, "message": message})

    return render(request, "utils/monitoring/recent_errors.html", {"errors": errors})
