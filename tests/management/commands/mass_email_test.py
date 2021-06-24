import sys
import time

from django.core.exceptions import SuspiciousOperation
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string

from accounts.models import User
from cobalt.settings import COBALT_HOSTNAME
from notifications.views import CobaltEmail
from tests.client_tests import ClientTest

EMAIL_BASE = "test_"
EMAIL_DOMAIN = "@gu3.com.au"
TEST_SIZE = 10
START_NUM = 81000
CONTENT = "I am a big test email to mimic production. Most of my size comes from the template"

class Command(BaseCommand):
    """
        Mass email test - creates lots of users and sends a lot of emails
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
                password="F1shcake",
                first_name=f"{EMAIL_BASE}{i}",
                last_name="TestUser",
                system_number=START_NUM + i,
                about="",
                pic=None,
            )
            user.save()
            user_list.append(user)
            print(f"Created used {user}")

        # Send emails
        email_sender = CobaltEmail()
        subject = "Bulk Email"
        body = CONTENT

        for recipient in user_list:
            context = {
                "name": recipient.first_name,
                "title1": f"Message from Someone",
                "title2": subject,
                "email_body": body,
                "host": COBALT_HOSTNAME,
            }

            html_msg = render_to_string(
                "notifications/email_with_2_headings.html", context
            )

            email_sender.queue_email(
                recipient.email,
                subject,
                html_msg,
                recipient,
            )

            print(f"Queued email to {recipient}")

            # send
        email_sender.send()

        time.sleep(100000000)


