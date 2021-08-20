from django.core.exceptions import SuspiciousOperation
from django.core.management.base import BaseCommand

from accounts.models import User
from cobalt.settings import COBALT_HOSTNAME

EMAIL_BASE = "test_"
EMAIL_DOMAIN = "@gu3.com.au"
TEST_SIZE = 2000
START_NUM = 8100000
CONTENT = (
    "I am a big test email to mimic production. Most of my size comes from the template"
)


class Command(BaseCommand):
    """
    Mass email test - creates lots of users for test sending
    Works with /accounts/test_email_send
    """

    def handle(self, *args, **options):

        if COBALT_HOSTNAME in ["myabf.com.au", "www.myabf.com.au"]:
            raise SuspiciousOperation(
                "Not for use in production. This cannot be used in a production system."
            )

        # Create users
        user_list = []
        for i in range(TEST_SIZE):
            user = User.objects.create_user(
                username="%s" % (START_NUM + i),
                email=f"{EMAIL_BASE}{i}{EMAIL_DOMAIN}",
                # email="m@rkguthrie.com",
                password="F1shcake",
                first_name=f"{EMAIL_BASE}{i}",
                last_name="TestUserEmailThing",
                system_number=START_NUM + i,
                about="",
                pic=None,
            )
            user.save()
            user_list.append(user)
            print(f"Created used {user}")
