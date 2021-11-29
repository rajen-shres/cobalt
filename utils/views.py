import csv
import datetime
import os
from random import randint
from time import sleep

import pytz
import requests
from django.apps import apps
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction, connection, ProgrammingError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from geopy.geocoders import Nominatim

from accounts.models import User
from cobalt.settings import TIME_ZONE
from events.events_views.core import events_status_summary
from forums.views import forums_status_summary
from notifications.views import notifications_status_summary
from payments.payments_views.core import payments_status_summary
from utils.utils import cobalt_paginator
from .models import Batch, Lock
from importlib import import_module

# from importlib import import_module


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
