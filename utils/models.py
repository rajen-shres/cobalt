""" Utilities.

    This handles the models for home things such as batch processing.

"""
from datetime import timedelta

import pytz
from django.db import models
from django.utils import timezone
from cobalt.settings import HOSTNAME, TIME_ZONE

JOB_STATUSES = [
    ("Started", "Job started"),
    ("Success", "Job completed successfully"),
    ("Failed", "Job failed to complete"),
]


class Batch(models.Model):
    """Batch job status"""

    name = models.CharField("Name", max_length=30)
    run_date = models.DateTimeField("Run Date", default=timezone.now)
    start_time = models.DateTimeField("Start Time", default=timezone.now)
    end_time = models.DateTimeField("End Time", null=True, blank=True)
    instance = models.CharField("Instance", max_length=10, null=True, blank=True)
    node = models.CharField("Node running job", max_length=50, default=HOSTNAME)
    job_status = models.CharField(
        "Job Status", choices=JOB_STATUSES, max_length=10, default="Started"
    )

    class Meta:
        verbose_name_plural = "Batches"

    def __str__(self):
        if self.instance:
            return f"{self.name}[{self.instance}] - {self.run_date} - {self.job_status}"
        else:
            return f"{self.name} - {self.run_date} - {self.job_status}"


class Lock(models.Model):
    """Equivalent of a lock file for a distributed environment"""

    topic = models.CharField(max_length=100, unique=True)
    lock_created_time = models.DateTimeField(default=timezone.now)
    lock_open_time = models.DateTimeField(null=True, blank=True)
    owner = models.CharField(max_length=200)

    def __str__(self):
        if not self.lock_open_time:
            return f"Unlocked - {self.topic}"
        local_dt = timezone.localtime(self.lock_open_time, pytz.timezone(TIME_ZONE))
        return f"Locked - {self.topic} - Expires {local_dt:%d/%m/%Y %H:%M %Z}"


class Seat(models.TextChoices):
    NORTH = "N", "North"
    SOUTH = "S", "South"
    EAST = "E", "East"
    WEST = "W", "West"


class Slug(models.Model):
    """This maps short names to redirects. e.g. localhost/my-nice-slug -> localhost/events/5"""

    slug = models.CharField(max_length=50, unique=True)
    redirect_path = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.slug} -> {self.redirect_path}"
