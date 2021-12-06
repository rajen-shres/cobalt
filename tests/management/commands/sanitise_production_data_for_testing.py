""" Script to sanitise prod data so we can use it for testing """
from django.core.exceptions import SuspiciousOperation
from post_office.models import Email, STATUS

from cobalt.settings import (
    RBAC_EVERYONE,
    TIME_ZONE,
    DUMMY_DATA_COUNT,
    TBA_PLAYER,
    COBALT_HOSTNAME,
)
from accounts.models import User
from django.core.management.base import BaseCommand
from accounts.management.commands.accounts_core import create_fake_user
from forums.models import Post, Comment1, Comment2, LikePost, LikeComment1, LikeComment2
import random
from essential_generators import DocumentGenerator
import datetime
import pytz
from django.utils.timezone import make_aware, now
import glob
import sys
from inspect import currentframe, getframeinfo
from importlib import import_module


class Command(BaseCommand):
    def handle(self, *args, **options):
        if COBALT_HOSTNAME in ["myabf.com.au", "www.myabf.com.au"]:
            raise SuspiciousOperation(
                "Not for use in production. This cannot be used in a production system."
            )

        print("Cleaning production data to use for testing")

        print("Deleting queued email...")
        Email.objects.exclude(status=STATUS.sent).exclude(status=STATUS.failed).delete()

        print("Changing email addresses...")
        User.objects.all().update(email="a@b.com")
