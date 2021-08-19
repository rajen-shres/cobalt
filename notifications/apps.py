from django.apps import AppConfig
from django.utils import timezone
import logging

from cobalt.settings import COBALT_HOSTNAME

logger = logging.getLogger("cobalt")


class NotificationsConfig(AppConfig):
    name = "notifications"

    def ready(self):
        """Called when Django starts up

        For more information look in the docs at notifications_overview

        This handles the signals from django-ses when notifications are received from SES.

        We expect to find two header items that are attached when we sent:
            COBALT_ID - pk of the Django Post Office email
            COBALT_ENV - environment (test, uat, prod)

        BE CAREFUL!!! This can impact production, it is the only part of Cobalt that is
                      shared between all environments.

        """
        # Can't import at top of file - Django won't be ready yet
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

        def _get_message_id(mail_obj):
            """Utility to get the message_id from the message"""

            # Get headers from mail_obj - headers is a list of headers
            headers = mail_obj["headers"]

            for header in headers:
                if header["name"] == "Message-ID":
                    return header["value"]

            return None

        @receiver(send_received)
        def send_handler(sender, mail_obj, send_obj, raw_message, *args, **kwargs):
            """Handle SES incoming info"""

            print(mail_obj, flush=True)

            message_id = _get_message_id(mail_obj)

            logger.info(f"SENT: Received Message-ID: {message_id}")

            post_office_email = PostOfficeEmail.objects.get(message_id=message_id)
            snooper = Snooper.objects.get_or_create(post_office_email=post_office_email)
            snooper.ses_sent_at = timezone.now()
            snooper.save()

        @receiver(delivery_received)
        def delivery_handler(
            sender, mail_obj, delivery_obj, raw_message, *args, **kwargs
        ):
            """Handle SES incoming info"""

            message_id = _get_message_id(mail_obj)

            logger.info(f"DELIVER: Received Message-ID: {message_id}")

            try:
                post_office_email = PostOfficeEmail.objects.get(message_id=message_id)
                snooper = Snooper.objects.get_or_create(
                    post_office_email=post_office_email
                )
                snooper.ses_delivered_at = timezone.now()
                snooper.save()
            except AttributeError:
                logger.info(f"DELIVER: No matching message found for :{message_id}")

        @receiver(open_received)
        def open_handler(sender, mail_obj, open_obj, raw_message, *args, **kwargs):
            """Handle SES incoming info"""

            message_id = _get_message_id(mail_obj)

            logger.info(f"OPEN: Received Message-ID: {message_id}")

            try:
                post_office_email = PostOfficeEmail.objects.get(message_id=message_id)
                snooper = Snooper.objects.filter(
                    post_office_email=post_office_email
                ).first()
                snooper.ses_opened_at = timezone.now()
                snooper.save()
            except AttributeError:
                logger.info(f"OPEN: No matching message found for :{message_id}")

        @receiver(click_received)
        def click_handler(sender, mail_obj, click_obj, raw_message, *args, **kwargs):
            """Handle SES incoming info"""

            message_id = _get_message_id(mail_obj)

            logger.info(f"CLICK: Received Message-ID: {message_id}")

            try:
                post_office_email = PostOfficeEmail.objects.get(message_id=message_id)
                snooper = Snooper.objects.filter(
                    post_office_email=post_office_email
                ).first()
                snooper.ses_clicked_at = timezone.now()
                snooper.save()
            except AttributeError:
                logger.info(f"CLICK: No matching message found for :{message_id}")

        @receiver(bounce_received)
        def bounce_handler(sender, mail_obj, bounce_obj, raw_message, *args, **kwargs):
            """Handle SES incoming info"""

            message_id = _get_message_id(mail_obj)

            logger.info(f"BOUNCE: Received Message-ID: {message_id}")
            logger.error("Email Bounced")

            try:
                post_office_email = PostOfficeEmail.objects.get(message_id=message_id)
                logger.error(f"ID: {post_office_email.id}")
            except AttributeError:
                logger.info(f"BOUNCE: No matching message found for :{message_id}")

        @receiver(complaint_received)
        def complaint_handler(
            sender, mail_obj, complaint_obj, raw_message, *args, **kwargs
        ):
            """Handle SES incoming info"""

            message_id = _get_message_id(mail_obj)

            logger.info(f"COMPLAINT: Received Message-ID: {message_id}")
            logger.error("Email Complaint")

            try:
                post_office_email = PostOfficeEmail.objects.get(message_id=message_id)
                logger.error(f"ID: {post_office_email.id}")
            except AttributeError:
                logger.info(f"COMPLAINT: No matching message found for :{message_id}")
