import os
import sys

from django.core.exceptions import SuspiciousOperation
from django.core.management.base import BaseCommand

from cobalt.settings import COBALT_HOSTNAME
from tests.simple_selenium import SimpleSelenium
from tests.simple_selenium_parser import simple_selenium_parser
from tests.test_manager import CobaltTestManagerIntegration


class Command(BaseCommand):
    def add_arguments(self, parser):

        parser.add_argument("--app", help="App name e.g. payments.")
        parser.add_argument("--password", help="password for user")
        parser.add_argument("--script", help="script to execute")
        parser.add_argument("--browser", help="Browser - default is chrome")
        parser.add_argument(
            "--base_url", help="Base url for server e.g. http://127.0.0.1:8088"
        )
        parser.add_argument(
            "--headless", help="Specify an value to run browser in the background"
        )

    def handle(self, *args, **options):

        # app = options["app"]
        # browser = options["browser"]
        base_url = options["base_url"]
        password = options["password"]
        script = options["script"]

        if not base_url:
            base_url = "https://test.myabf.com.au"

        simple_selenium_parser(script, base_url=base_url, password=password)
