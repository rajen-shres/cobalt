""" Script to sanitise prod data so we can use it for testing """
from django.core.exceptions import SuspiciousOperation
from post_office.models import Email, STATUS

from cobalt.settings import (
    COBALT_HOSTNAME,
)
from accounts.models import User
from django.core.management.base import BaseCommand


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
