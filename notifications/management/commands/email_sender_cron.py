""" Cron job to pick up any lost emails and send them """
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.html import strip_tags
from cobalt.settings import DEFAULT_FROM_EMAIL
from logs.views import log_event
from notifications.models import Email
from datetime import datetime, timedelta
from random import randint
from time import sleep


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("email_sender_cron.py is starting...")

        # in a multi-node environment we might clash with another node so sleep a random time 0-10 secs
        sleep(randint(0, 10))
        print("email_sender_cron.py is running...")

        ref_date = timezone.now() - timedelta(minutes=1)
        emails = Email.objects.filter(status="Queued").filter(created_date__lt=ref_date)

        for email in emails:

            if email.reply_to is None:
                email.reply_to = ""

            plain_message = strip_tags(email.message)

            msg = EmailMultiAlternatives(
                email.subject,
                plain_message,
                to=[email.recipient],
                from_email=DEFAULT_FROM_EMAIL,
                reply_to=[email.reply_to],
            )

            msg.attach_alternative(email.message, "text/html")

            msg.send()

            email.status = "Sent"
            email.sent_date = timezone.now()
            email.save()

            print(f"Cron sent email to {email.recipient}")

        if emails:

            log_event(
                user=None,
                severity="CRITICAL",
                source="Notifications",
                sub_source="Email",
                message="Cron picked up stuck email",
            )
