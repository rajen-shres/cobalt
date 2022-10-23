import csv
import datetime
import os
import re
import subprocess
from random import randint
from time import sleep

import boto3
import pytz
import requests
from dateutil.tz import tz
from django.apps import apps
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction, connection, ProgrammingError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.safestring import mark_safe
from geopy.geocoders import Nominatim
from html5lib.treewalkers import pprint

from accounts.models import User
from cobalt.settings import (
    TIME_ZONE,
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION_NAME,
    COBALT_HOSTNAME,
)
from events.views.core import events_status_summary
from forums.views import forums_status_summary
from notifications.views.admin import notifications_status_summary
from payments.views.core import payments_status_summary
from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden
from utils.utils import cobalt_paginator
from .models import Batch, Lock, Slug

# from importlib import import_module
# This line sometimes get removed by something that thinks we don't need it, but we do
from importlib import import_module


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
        return False, "Error - environment not found"

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
        return False, "No environment found", {}

    # Now get the sessions for the environment
    settings = eb_client.describe_configuration_settings(
        ApplicationName="cobalt", EnvironmentName=aws_environment_name
    )

    # Just get the environment variables, ignore the rest
    settings_dict = {}

    for setting in settings["ConfigurationSettings"][0]["OptionSettings"]:
        if setting["Namespace"] == "aws:elasticbeanstalk:application:environment":
            settings_dict[setting["OptionName"]] = setting["Value"]

    return True, aws_environment_name, settings_dict


@login_required
def user_activity(request):
    """show user activity figures"""

    users = (
        User.objects.order_by("-last_activity")
        .exclude(last_activity=None)
        .exclude(id=request.user.id)
    )[:100]

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

    return render(
        request,
        "utils/user_activity.html",
        {
            "users": users,
            "last_5m": last_5m,
            "last_1hr": last_1hr,
            "last_day": last_day,
            "last_week": last_week,
            "last_month": last_month,
        },
    )


@login_required()
def geo_location(request, location):
    """return lat and long for a text address"""

    try:
        geolocator = Nominatim(user_agent="cobalt")
        loc = geolocator.geocode(location)
        html = {"lat": loc.latitude, "lon": loc.longitude}
        data_dict = {"data": html}
        return JsonResponse(data=data_dict, safe=False)
    except:  # noqa E722
        return JsonResponse({"data": {"lat": None, "lon": None}}, safe=False)


class CobaltBatch:
    """Class to handle batch jobs within Cobalt. We use cron (or whatever you
    like) to trigger the jobs which are set up using django-extensions.

    Args:
        name(str) - name of this batch job
        schedule(str) - Daily, Hourly etc
        instance(str) - identifier for this run if runs can happen multiple time a day
        rerun(bool) - true to allow this to overwrite previous entry

    Returns:
        CobaltBatch
    """

    # TODO: find a way to rerun jobs
    # TODO: handle hourly etc - currently only lets us run once a day

    def __init__(self, name, schedule, instance=None, rerun=False):

        self.name = name
        self.schedule = schedule
        self.instance = instance
        self.rerun = rerun

    def start(self):
        # sleep for a random time to avoid all nodes hitting db at once
        sleep(randint(0, 1))

        match = Batch.objects.filter(
            name=self.name, instance=self.instance, run_date__date=timezone.now().date()
        ).count()

        if match:  # this job is already running on another node
            return False

        else:  # not running
            self.batch = Batch()
            self.batch.name = self.name
            self.batch.schedule = self.schedule
            self.batch.instance = self.instance
            self.batch.save()
            return True

    def finished(self, status="Success"):
        print("Called finished  ")
        self.batch.job_status = status
        self.batch.end_time = timezone.now()
        self.batch.save()


@user_passes_test(lambda u: u.is_superuser)
def batch(request):
    events_list = Batch.objects.all().order_by("-run_date", "-start_time", "-end_time")

    things = cobalt_paginator(request, events_list)

    return render(request, "utils/batch.html", {"things": things})


@login_required()
def status(request):
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
    # build_date = timezone.localtime(utc_build_date, TZ)
    build_date = TZ.localize(utc_build_date)

    return render(
        request,
        "utils/status.html",
        {
            "users": users,
            "payments": payments,
            "notifications": notifications,
            "events": events,
            "forums": forums,
            "build_date": build_date,
        },
    )


def download_csv(self, request, queryset):
    """Copied from Stack Overflow - generic CSV download"""

    model = queryset.model
    model_fields = model._meta.fields + model._meta.many_to_many
    field_names = [field.name for field in model_fields]

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="export.csv"'

    # the csv writer
    writer = csv.writer(response)
    # Write a first row with header information
    writer.writerow(field_names)
    # Write data rows
    for row in queryset:
        values = []
        for field in field_names:
            value = getattr(row, field)

            values.append(value)
        writer.writerow(values)

    return response


def masterpoint_query(query):
    """Generic function to talk to the masterpoints server and return data

    Takes in a SQLServer query e.g. "select count(*) from table"

    Returns an iterable, either an empty list or the response from the server.

    In case there is a problem connecting to the server, this will do everything it
    can to fail silently.

    """

    # Try to load data from MP Server

    try:
        response = requests.get(query, timeout=10).json()
    except Exception as exc:
        print(exc)
        response = []

    return response


class CobaltLock:
    """handle running one thing at a time in a multi-node environment"""

    def __init__(self, topic: str, expiry: int = 15):
        """
        Args:
            topic: name of this lock
            expiry: time in minutes to keep the lock closed for. After this even if
                    open it will be considered expired (assume process died)
        """

        self.topic = topic
        self.expiry = expiry
        self._locked = False

    @transaction.atomic
    def get_lock(self):
        """Try to get a lock, returns True or False"""

        lock = Lock.objects.select_for_update().filter(topic=self.topic).first()

        if lock:  # Lock found

            if lock.lock_open_time and lock.lock_open_time > timezone.now():
                return False

            lock.lock_created_time = timezone.now()
            open_time = timezone.now() + datetime.timedelta(minutes=self.expiry)
            hostname = os.popen("hostname 2>/dev/null").read().strip()
            lock.lock_open_time = open_time
            lock.owner = hostname
            lock.save()

        else:  # Create lock

            open_time = timezone.now() + datetime.timedelta(minutes=self.expiry)
            hostname = os.popen("hostname 2>/dev/null").read().strip()
            Lock(lock_open_time=open_time, topic=self.topic, owner=hostname).save()

        self._locked = True
        return True

    @transaction.atomic
    def free_lock(self):
        """release lock"""

        if not self._locked:
            return

        lock = Lock.objects.select_for_update().filter(topic=self.topic).first()
        if not lock:
            return
        lock.lock_open_time = None
        lock.save()


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
        "utils/database_view.html",
        {"db_sizes": db_sizes, "total_size": total_size, "total_rows": total_rows},
    )


def check_slug_is_free(slug):
    """Check if a slug is in use or not"""

    return not Slug.objects.filter(slug=slug).exists()


def create_new_slug(slug, redirect_path):
    """create a slug if it doesn't already exist"""

    if Slug.objects.filter(slug=slug).exists():
        return False

    Slug(slug=slug, redirect_path=redirect_path).save()
    return True


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

    return render(request, "utils/recent_errors.html", {"errors": errors})


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
        "utils/admin_show_aws_infrastructure_info.html",
        {"environments": environments},
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
        "utils/admin_show_database_details_htmx.html",
        {"db_details": db_details, "cpu": cpu},
    )


@login_required()
def admin_system_activity(request):
    """Show basic info about user activity"""

    return render(request, "utils/admin_system_activity.html")


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
        request, "utils/admin_system_activity_nginx_htmx.html", {"log_data": log_data}
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
        "utils/admin_system_activity_cobalt_messages_htmx.html",
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
        "utils/admin_system_activity_users_htmx.html",
        {"last_activity": last_activity},
    )


@login_required()
def admin_system_settings(request):
    """Manage system-wide settings"""

    role = "system.admin.edit"
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    # Get aws name of this system
    call_status, aws_environment_name, settings = _get_aws_environment()

    # Quit if we got an error
    if not call_status:
        return render(
            request,
            "utils/admin_system_settings.html",
            {"message": aws_environment_name},
        )

    # Get the setting we are interested in
    # fish_setting = settings.get("FISH_SETTING") == "ON"
    # disable_playpen = settings.get("DISABLE_PLAYPEN") == "ON"
    # maintenance_mode = settings.get("MAINTENANCE_MODE") == "ON"

    # Create AWS client
    eb_client = boto3.client(
        "elasticbeanstalk",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION_NAME,
    )

    response = eb_client.update_environment(
        ApplicationName="cobalt",
        EnvironmentName="cobalt-test-black",
        OptionSettings=[
            {
                "Namespace": "aws:elasticbeanstalk:application:environment",
                "OptionName": "FISH_SETTING",
                "Value": "updated",
            }
        ],
    )

    print(response)

    return render(
        request,
        "utils/admin_system_settings.html",
        {
            "aws_environment_name": aws_environment_name,
            "settings": settings,
            "response": response,
        },
    )
