from datetime import time

import psycopg2
from django.apps import AppConfig
from django.db import ProgrammingError
from django.utils import timezone


class NotificationsConfig(AppConfig):
    name = "notifications"

    def ready(self):
        """Called when Django starts up

        We use the model EmailThread to record what email threads are running.
        After a restart we clear the table.

        For more information look in the docs at notifications_overview

        """
        from django.dispatch import receiver
        from django_ses.signals import (
            send_received,
            delivery_received,
            open_received,
            click_received,
            bounce_received,
            complaint_received,
        )
        from notifications.models import Snooper
        from post_office.models import Email as PostOfficeEmail

        # Can't import at top of file - Django won't be ready yet
        # Also if this is a clean install migrate won't have been run so catch an error and ignore

        try:
            from .models import EmailThread

            EmailThread.objects.all().delete()

        except (psycopg2.errors.UndefinedTable, ProgrammingError):
            # Should only happen if this a clean install (dev, test, UAT). Reasonably safe to ignore.
            pass

        def _get_email_id(mail_obj):
            """Utility to get our email id from the mail object. We plant this mail id in the header
            on the way out"""

            # Get headers from mail_obj - headers is a list of headers
            headers = mail_obj["headers"]

            # Get the mail_id from the headers
            for header in headers:
                if header["name"] == "COBALT_ID":
                    return header["value"]

            return None

        @receiver(send_received)
        def send_handler(sender, mail_obj, send_obj, raw_message, *args, **kwargs):
            """Handle SES incoming info"""

            mail_id = _get_email_id(mail_obj)
            if not mail_id:
                return

            print("\n\nSend: Mail ID:", mail_id, flush=True)

            post_office_email = PostOfficeEmail.objects.get(pk=mail_id)
            snooper = Snooper.objects.filter(
                post_office_email=post_office_email
            ).first()
            snooper.ses_sent_at = timezone.now()
            snooper.save()

        @receiver(delivery_received)
        def delivery_handler(
            sender, mail_obj, delivery_obj, raw_message, *args, **kwargs
        ):
            """Handle SES incoming info"""

            mail_id = _get_email_id(mail_obj)
            if not mail_id:
                return

            print("\n\ndelivery: Mail ID:", mail_id, flush=True)

            post_office_email = PostOfficeEmail.objects.get(pk=mail_id)
            snooper = Snooper.objects.filter(
                post_office_email=post_office_email
            ).first()
            snooper.ses_delivered_at = timezone.now()
            snooper.save()

        @receiver(open_received)
        def open_handler(sender, mail_obj, open_obj, raw_message, *args, **kwargs):
            """Handle SES incoming info"""

            mail_id = _get_email_id(mail_obj)
            if not mail_id:
                return

            print("\n\nopen: Mail ID:", mail_id, flush=True)

            post_office_email = PostOfficeEmail.objects.get(pk=mail_id)
            snooper = Snooper.objects.filter(
                post_office_email=post_office_email
            ).first()
            snooper.ses_opened_at = timezone.now()
            snooper.save()

        @receiver(click_received)
        def click_handler(sender, mail_obj, click_obj, raw_message, *args, **kwargs):
            """Handle SES incoming info"""

            mail_id = _get_email_id(mail_obj)
            if not mail_id:
                return

            print("\n\nclick: Mail ID:", mail_id, flush=True)

            post_office_email = PostOfficeEmail.objects.get(pk=mail_id)
            snooper = Snooper.objects.filter(
                post_office_email=post_office_email
            ).first()
            snooper.ses_clicked_at = timezone.now()
            snooper.save()

        @receiver(bounce_received)
        def bounce_handler(sender, mail_obj, bounce_obj, raw_message, *args, **kwargs):
            """Handle SES incoming info"""

            mail_id = _get_email_id(mail_obj)
            if not mail_id:
                return

            print("\n\nBOUNCE: Mail ID:", mail_id, flush=True)

        @receiver(complaint_received)
        def complaint_handler(
            sender, mail_obj, complaint_obj, raw_message, *args, **kwargs
        ):
            """Handle SES incoming info"""

            mail_id = _get_email_id(mail_obj)
            if not mail_id:
                return

            print("\n\nCOMPLAINT: Mail ID:", mail_id, flush=True)
