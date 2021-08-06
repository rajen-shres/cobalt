import os
import sys

from django.core.exceptions import SuspiciousOperation
from django.core.management.base import BaseCommand

from cobalt.settings import COBALT_HOSTNAME
from tests.test_manager import CobaltTestManager


class Command(BaseCommand):
    def add_arguments(self, parser):
        # Positional arguments

        parser.add_argument("--app", help="App name e.g. payments.")
        parser.add_argument("--browser", help="Browser - default is chrome")

    def handle(self, *args, **options):

        if COBALT_HOSTNAME in ["myabf.com.au", "www.myabf.com.au"]:
            raise SuspiciousOperation(
                "Not for use in production. This cannot be used in a production system."
            )

        # If we crash then we leave dead browser sessions, try to kill them off
        os.system('pkill - f"(chrome)?(--headless)"')
        os.system('pkill - f"(firefox)?(--headless)"')

        app = options["app"]
        browser = options["browser"]

        # create testManager to oversee things
        manager = CobaltTestManager(app, browser)
        manager.run()
        manager.report()
