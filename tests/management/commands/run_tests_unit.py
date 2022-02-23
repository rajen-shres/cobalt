import os
import sys

from django.core.exceptions import SuspiciousOperation
from django.core.management.base import BaseCommand

from cobalt.settings import COBALT_HOSTNAME
from tests.test_manager import CobaltTestManagerUnit


class Command(BaseCommand):
    def add_arguments(self, parser):
        # Positional arguments

        parser.add_argument("--app", help="App name e.g. payments.")

    def handle(self, *args, **options):
        if COBALT_HOSTNAME in ["myabf.com.au", "www.myabf.com.au"]:
            raise SuspiciousOperation(
                "Not for use in production. This cannot be used in a production system."
            )

        app = options["app"]

        # create testManager to oversee things
        manager = CobaltTestManagerUnit(app)
        manager.run()
        with open("/tmp/test-output.html", "w") as html_file:
            html_file.write(manager.report_html())
        os.system("utils/cgit/tools/open_report.sh")
