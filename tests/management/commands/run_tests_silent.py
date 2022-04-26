import os
import sys

from django.core.exceptions import SuspiciousOperation
from django.core.management.base import BaseCommand

from cobalt.settings import COBALT_HOSTNAME
from tests.test_manager import CobaltTestManagerIntegration, CobaltTestManagerUnit


class Command(BaseCommand):
    def handle(self, *args, **options):

        if COBALT_HOSTNAME in ["myabf.com.au", "www.myabf.com.au"]:
            raise SuspiciousOperation(
                "Not for use in production. This cannot be used in a production system."
            )

        # Unit Tests
        manager = CobaltTestManagerUnit()
        manager.run()
        unit_test_pass = bool(manager.overall_success)

        # Integration Tests
        manager = CobaltTestManagerIntegration(
            app=None, browser=None, base_url="http://127.0.0.1:8888", headless=True
        )
        manager.run()
        integration_test_pass = bool(manager.overall_success)

        print("Unit:", unit_test_pass)
        print("Integration:", integration_test_pass)
