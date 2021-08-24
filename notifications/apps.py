from django.apps import AppConfig
from django.utils import timezone
import logging

# TODO: This code always makes me want to take a shower after I look at it.
# TODO: I'm not going to fix it. I'm just going to have a shower.

logger = logging.getLogger("cobalt")


class NotificationsConfig(AppConfig):
    """
    This uses the ready() function of AppConfig to register to handle signals for Django SES.
    It has to do this because we need Django to be ready before we can register them.

    Signals are a bit of a nasty way to do things but are the only way to get notified by
    Django SES that we have an incoming event to handle.

    There is one handler per event - send, deliver, open, click, bounce, complaint

    There is a weird problem where it won't work unless DEBUG is on. It seems that within Django
    in dispatch/dispatcher.py in the function connect, if DEBUG is true then it tries to check that
    the receiver (us) accepts **kwargs (we do). Without this check Django SES doesn't call us.
    To get around this, we call the same function that connect calls - func_accepts_kwargs once
    for each receiving function.
    """

    name = "notifications"

    def ready(self):
        """Called when Django starts up

        For more information look in the docs at notifications_overview

        This handles the signals from django-ses when notifications are received from SES.

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
        from logs.views import log_event
        from django.utils.inspect import func_accepts_kwargs
        from support.helpdesk import create_ticket_api

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
            """Handle SES incoming info. Not that none of these will work without the calls at the bottom"""

            message_id = _get_message_id(mail_obj)

            logger.info(f"SENT: Received Message-ID: {message_id}")

            try:
                post_office_email = PostOfficeEmail.objects.get(message_id=message_id)
                snooper, _ = Snooper.objects.get_or_create(
                    post_office_email=post_office_email
                )
                snooper.ses_sent_at = timezone.now()
                snooper.save()
                logger.info(f"SENT: Processed Message-ID: {message_id}")
            except (AttributeError, PostOfficeEmail.DoesNotExist):
                logger.info(f"SENT: No matching message found for :{message_id}")

        @receiver(delivery_received)
        def delivery_handler(
            sender, mail_obj, delivery_obj, raw_message, *args, **kwargs
        ):
            """Handle SES incoming info"""

            message_id = _get_message_id(mail_obj)

            logger.info(f"DELIVER: Received Message-ID: {message_id}")

            try:
                post_office_email = PostOfficeEmail.objects.get(message_id=message_id)
                snooper, _ = Snooper.objects.get_or_create(
                    post_office_email=post_office_email
                )
                snooper.ses_delivered_at = timezone.now()
                snooper.save()
                logger.info(f"DELIVER: Processed Message-ID: {message_id}")
            except (AttributeError, PostOfficeEmail.DoesNotExist):
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
                snooper.ses_last_opened_at = timezone.now()
                snooper.ses_open_count += 1
                snooper.save()
                logger.info(f"OPEN: Processed Message-ID: {message_id}")
            except (AttributeError, PostOfficeEmail.DoesNotExist):
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
                snooper.ses_last_clicked_at = timezone.now()
                snooper.ses_clicked_count += 1
                snooper.save()
                logger.info(f"CLICK: Processed Message-ID: {message_id}")
            except (AttributeError, PostOfficeEmail.DoesNotExist):
                logger.info(f"CLICK: No matching message found for :{message_id}")

        @receiver(bounce_received)
        def bounce_handler(sender, mail_obj, bounce_obj, raw_message, *args, **kwargs):
            """Handle SES incoming info"""

            message_id = _get_message_id(mail_obj)

            logger.info(f"BOUNCE: Received Message-ID: {message_id}")

            try:
                post_office_email = PostOfficeEmail.objects.get(message_id=message_id)
                our_id = post_office_email.id
                logger.error(f"ID: {post_office_email.id}")
            except (AttributeError, PostOfficeEmail.DoesNotExist):
                logger.info(f"BOUNCE: No matching message found for :{message_id}")
                our_id = None

            message = f"Bounce received: bounce type: {bounce_obj['bounceType']}, bounce sub-type: {bounce_obj['bounceSubType']} bounced_recipients: {bounce_obj['bouncedRecipients']}"

            logger.error(message)

            # log event
            log_event(
                user=None,
                severity="CRITICAL",
                source="Notifications",
                sub_source="Email",
                message=message,
            )

            # Raise a ticket
            create_ticket_api(
                title=f"Email Bounce from {bounce_obj['bouncedRecipients']}"[:80],
                description=f"Email Bounce Received.\n\n"
                f"bounce type: {bounce_obj['bounceType']}\n"
                f"bounce sub-type: {bounce_obj['bounceSubType']}\n"
                f"Message ID: {message_id}\n"
                f"Our Post Office ID: {our_id}\n"
                f" bounced_recipients: {bounce_obj['bouncedRecipients']}\n\nPlease investigate.",
            )

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
            except (AttributeError, PostOfficeEmail.DoesNotExist):
                logger.info(f"COMPLAINT: No matching message found for :{message_id}")

        # See comments at the top of the file about this
        send_received.connect(send_handler)
        func_accepts_kwargs(send_handler)
        func_accepts_kwargs(delivery_handler)
        func_accepts_kwargs(open_handler)
        func_accepts_kwargs(click_handler)
        func_accepts_kwargs(bounce_handler)
        func_accepts_kwargs(complaint_handler)
