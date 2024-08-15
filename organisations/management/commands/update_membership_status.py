"""
Batch command to update time sensitive membership statuses

Should be run nightly soon after midnight via cron
Can be run at any time manually
"""

import logging

from django.db import transaction
from django.core.management.base import BaseCommand
from django.utils import timezone

from organisations.models import (
    MemberClubDetails,
    Organisation,
)
from organisations.club_admin_core import (
    perform_simple_action,
)

logger = logging.getLogger("cobalt")
today = timezone.now().date()


class Command(BaseCommand):
    help = "Periodic batch command to update time sensitive membership statuses"

    def get_club(self, club_id):
        """Chached lookup of club"""
        if club_id not in self.club_cache:
            club = Organisation.objects.get(pk=club_id)
            self.club_cache[club_id] = club
        return self.club_cache[club_id]

    def handle(self, *args, **options):

        logger.info("Membership status update starting")

        # lapse any members passed their due payment dates

        processed = 0
        errored = 0

        self.club_cache = {}

        overdue_member_list = (
            MemberClubDetails.objects.exclude(latest_membership__due_date=None)
            .filter(
                membership_status=MemberClubDetails.MEMBERSHIP_STATUS_DUE,
                latest_membership__due_date__lt=today,
            )
            .values_list("club_id", "system_number")
        )

        for club_id, system_number in overdue_member_list:
            try:
                with transaction.atomic():
                    perform_simple_action(
                        "lapsed", self.get_club(club_id), system_number
                    )
                processed += 1
            except Exception as e:
                logger.error(
                    f"Exception lapsing overdue {system_number} of {self.get_club(club_id)}: {e}"
                )
                errored += 1

        # lapse any members who have passed their paid_unit_date

        expired_member_list = (
            MemberClubDetails.objects.exclude(latest_membership__paid_until_date=None)
            .filter(
                membership_status=MemberClubDetails.MEMBERSHIP_STATUS_CURRENT,
                latest_membership__paid_until_date__lt=today,
            )
            .values_list("club_id", "system_number")
        )

        for club_id, system_number in expired_member_list:
            try:
                with transaction.atomic():
                    perform_simple_action(
                        "lapsed", self.get_club(club_id), system_number
                    )
                processed += 1
            except Exception as e:
                logger.error(
                    f"Exception lapsing expired {system_number} of {self.get_club(club_id)}: {e}"
                )
                errored += 1

        logger.info(
            f"Membership status update complete. {processed} processed, {errored} errored"
        )
