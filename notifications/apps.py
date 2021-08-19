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

        def _get_email_id(mail_obj):
            """Utility to get our email id from the mail object. We plant this mail id in the header
            on the way out"""

            # Get headers from mail_obj - headers is a list of headers
            headers = mail_obj["headers"]

            # Get the mail_id from the headers
            email_id = None
            cobalt_env = None

            for header in headers:
                if header["name"] == "COBALT_ID":
                    email_id = header["value"]
                if header["name"] == "COBALT_ENV":
                    cobalt_env = header["value"]

            return email_id, cobalt_env

        def _no_header_id(mail_obj, origin):
            """Handle emails without our header id being present"""

            logger.info(
                f"{origin}: Unknown email without id. Details follow if available."
            )
            try:
                logger.info(
                    f"{mail_obj['destination']} - {mail_obj['commonHeaders']['subject']}",
                )
            except KeyError:
                logger.info("Details not found")

        @receiver(send_received)
        def send_handler(sender, mail_obj, send_obj, raw_message, *args, **kwargs):
            """Handle SES incoming info"""

            mail_id, cobalt_env = _get_email_id(mail_obj)
            if cobalt_env != COBALT_HOSTNAME:
                logger.info("Message is not for this environment:", cobalt_env)
                return

            if not mail_id:
                _no_header_id(mail_obj, "SEND")
                return

            logger.info(f"Send: Mail ID: {mail_id}")

            try:
                post_office_email = PostOfficeEmail.objects.get(pk=mail_id)
                snooper = Snooper.objects.filter(
                    post_office_email=post_office_email
                ).first()
                snooper.ses_sent_at = timezone.now()
                snooper.save()
            except AttributeError:
                logger.info("SENT: Error. email with id:", mail_id)

        @receiver(delivery_received)
        def delivery_handler(
            sender, mail_obj, delivery_obj, raw_message, *args, **kwargs
        ):
            """Handle SES incoming info"""

            mail_id, cobalt_env = _get_email_id(mail_obj)
            if cobalt_env != COBALT_HOSTNAME:
                logger.info("Message is not for this environment:", cobalt_env)
                return

            if not mail_id:
                _no_header_id(mail_obj, "DELIVERY")
                return

            logger.info(f"delivery: Mail ID: {mail_id}")

            try:
                post_office_email = PostOfficeEmail.objects.get(pk=mail_id)
                snooper = Snooper.objects.filter(
                    post_office_email=post_office_email
                ).first()
                snooper.ses_delivered_at = timezone.now()
                snooper.save()
            except AttributeError:
                logger.info("DELIVER: Error. email with id:", mail_id)

        @receiver(open_received)
        def open_handler(sender, mail_obj, open_obj, raw_message, *args, **kwargs):
            """Handle SES incoming info"""

            mail_id, cobalt_env = _get_email_id(mail_obj)
            if cobalt_env != COBALT_HOSTNAME:
                logger.info("Message is not for this environment:", cobalt_env)
                return

            if not mail_id:
                _no_header_id(mail_obj, "OPEN")
                return

            logger.info(f"open: Mail ID: {mail_id}")

            try:
                post_office_email = PostOfficeEmail.objects.get(pk=mail_id)
                snooper = Snooper.objects.filter(
                    post_office_email=post_office_email
                ).first()
                snooper.ses_opened_at = timezone.now()
                snooper.save()
            except AttributeError:
                logger.info(f"OPEN: Error. email with id:{mail_id}")

        @receiver(click_received)
        def click_handler(sender, mail_obj, click_obj, raw_message, *args, **kwargs):
            """Handle SES incoming info"""

            mail_id, cobalt_env = _get_email_id(mail_obj)
            if cobalt_env != COBALT_HOSTNAME:
                logger.info(f"Message is not for this environment: {cobalt_env}")
                return

            if not mail_id:
                _no_header_id(mail_obj, "CLICK")
                return

            logger.info(f"click: Mail ID: {mail_id}")

            try:
                post_office_email = PostOfficeEmail.objects.get(pk=mail_id)
                snooper = Snooper.objects.filter(
                    post_office_email=post_office_email
                ).first()
                snooper.ses_clicked_at = timezone.now()
                snooper.save()
            except AttributeError:
                logger.info(f"CLICK: Error. email with id: {mail_id}")

        @receiver(bounce_received)
        def bounce_handler(sender, mail_obj, bounce_obj, raw_message, *args, **kwargs):
            """Handle SES incoming info"""

            mail_id, cobalt_env = _get_email_id(mail_obj)
            if cobalt_env != COBALT_HOSTNAME:
                logger.info("Message is not for this environment:", cobalt_env)
                return

            if not mail_id:
                _no_header_id(mail_obj, "BOUNCE")
                return

            logger.info(f"BOUNCE: Mail ID: {mail_id}")

        @receiver(complaint_received)
        def complaint_handler(
            sender, mail_obj, complaint_obj, raw_message, *args, **kwargs
        ):
            """Handle SES incoming info"""

            mail_id, cobalt_env = _get_email_id(mail_obj)
            if cobalt_env != COBALT_HOSTNAME:
                logger.info("Message is not for this environment:", cobalt_env)
                return

            if not mail_id:
                _no_header_id(mail_obj, "COMPLAINT")
                return

            logger.info(f"COMPLAINT: Mail ID: {mail_id}")
