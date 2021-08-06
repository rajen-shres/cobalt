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
        parser.add_argument(
            "--base_url", help="Base url for server e.g. http://127.0.0.1:8088"
        )
        parser.add_argument(
            "--headless", help="Specify an value to run browser in the background"
        )

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
        base_url = options["base_url"]
        headless = options["headless"]

        # create testManager to oversee things
        manager = CobaltTestManager(app, browser, base_url, headless)
        manager.run()
        manager.report()
