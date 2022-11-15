""" Cron job to delete old notifications """
import logging

from dateutil.relativedelta import relativedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from notifications.models import Email, InAppNotification

logger = logging.getLogger("cobalt")


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("running delete_old_in_app_notifications...")

        three_months_ago = timezone.now() - relativedelta(months=3)
        notifications = InAppNotification.objects.filter(
            created_date__lt=three_months_ago
        )
        logger.info(f"Deleting {len(notifications)} InAppNotifications.")
        notifications.delete()
