from django.core.exceptions import SuspiciousOperation
from django.core.management.base import BaseCommand

from cobalt.settings import COBALT_HOSTNAME
from tests.client_tests import ClientTest


class Command(BaseCommand):
    def handle(self, *args, **options):

        if COBALT_HOSTNAME in ["myabf.com.au", "www.myabf.com.au"]:
            raise SuspiciousOperation(
                "Not for use in production. This cannot be used in a production system."
            )

        c=ClientTest()
        if not c.run():
            c.report()
            html = c.report_html()
