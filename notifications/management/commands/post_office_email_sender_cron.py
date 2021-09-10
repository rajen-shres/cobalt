""" Cron job to send email """
import logging

from django.core.management.base import BaseCommand
from post_office.mail import send_queued

from utils.views import CobaltLock

logger = logging.getLogger("cobalt")


class Command(BaseCommand):
    def handle(self, *args, **options):
        """If we can get a lock on the email topic then send emails

        Django Post Office using file locks for controlling its cron,
        we can't use that in a distributed environment so we do our own locking.

        """

        logger.info("Post Office cron looking for work")

        lock = CobaltLock("email")
        if lock.get_lock():
            send_queued(processes=1)
            lock.free_lock()
        else:
            logger.info("Topic: 'email' is currently locked")
