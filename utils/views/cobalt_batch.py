from random import randint
from time import sleep

from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render

from django.utils import timezone

from utils.models import Batch
from utils.utils import cobalt_paginator


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
