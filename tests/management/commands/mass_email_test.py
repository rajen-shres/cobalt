from django.core.exceptions import SuspiciousOperation
from django.core.management.base import BaseCommand

from accounts.models import User
from cobalt.settings import COBALT_HOSTNAME


TEST_SIZE = 100
START_NUM = 1_000_000


class Command(BaseCommand):
    """
    Mass email test - creates lots of users for test sending
    See confluence for details on how to test
    """

    def handle(self, *args, **options):

        if COBALT_HOSTNAME in ["myabf.com.au", "www.myabf.com.au"]:
            raise SuspiciousOperation(
                "Not for use in production. This cannot be used in a production system."
            )

        # Create users
        for i in range(TEST_SIZE):
            user = User.objects.create_user(
                username="%s" % (START_NUM + i),
                email="success@simulator.amazonses.com",
                password="F1shcake",
                first_name=f"Someone_{i}",
                last_name="TestUserEmailThing",
                system_number=START_NUM + i,
                about="",
                pic=None,
            )
            user.save()
            print(f"Created used {user}")
