# from django.shortcuts import render
from geopy.geocoders import Nominatim
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
import json
from .models import Batch
from django.utils import timezone
from random import randint
from time import sleep
from django.contrib.auth.decorators import user_passes_test
from utils.utils import cobalt_paginator
from django.shortcuts import render, redirect, get_object_or_404
from notifications.views import send_cobalt_email
from cobalt.settings import COBALT_HOSTNAME, TIME_ZONE
from accounts.models import User
from payments.core import payments_status_summary
from notifications.views import notifications_status_summary
from events.core import events_status_summary
from forums.views import forums_status_summary
import datetime
import os
import pytz


@login_required
def user_activity(request):
    """ show user activity figures """

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
    """ return lat and long for a text address """

    geolocator = Nominatim(user_agent="cobalt")
    loc = geolocator.geocode(location)
    html = {"lat": loc.latitude, "lon": loc.longitude}
    data_dict = {"data": html}
    return JsonResponse(data=data_dict, safe=False)


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
    """ Basic system health """

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


# @login_required()
# def payment_status(request):
#     """ Basic payment health """
#
#     payments = None
#
#     return render(request, "utils/payment_status.html", {"payments": payments})
