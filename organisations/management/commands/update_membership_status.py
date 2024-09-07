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
    MemberMembershipType,
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

    def activate_future_dated(self, membership_id):
        """Process a future dated membership,
        known to have a start date of today or earlier"""

        membership = MemberMembershipType.objects.get(pk=membership_id)

        member_details = MemberClubDetails.objects.filter(
            club=membership.membership_type.organisation,
            system_number=membership.system_number,
        ).last()

        if membership.end_date is None or membership.end_date >= today:
            if membership.is_paid:
                membership.membership_state = (
                    MemberMembershipType.MEMBERSHIP_STATE_CURRENT
                )
            elif membership.due_date >= today:
                membership.membership_state = MemberMembershipType.MEMBERSHIP_STATE_DUE
            else:
                membership.membership_state = (
                    MemberMembershipType.MEMBERSHIP_STATE_LAPSED
                )
        else:
            membership.membership_state = MemberMembershipType.MEMBERSHIP_STATE_LAPSED

        membership.save()

        member_details.latest_membership = membership
        member_details.membership_status = membership.membership_state
        member_details.save()

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
                club__full_club_admin=True,
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
                club__full_club_admin=True,
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

        # check for any future dated memberships that should become active

        future_membership_list = (
            MemberMembershipType.objects.filter(
                membership_state=MemberMembershipType.MEMBERSHIP_STATE_FUTURE,
                start_date__lte=today,
                membership_type__organisation__full_club_admin=True,
            )
            .order_by("start_date")
            .values_list(
                "id",
                flat=True,
            )
        )

        for membership_id in future_membership_list:
            try:
                with transaction.atomic():
                    self.activate_future_dated(membership_id)
                processed += 1
            except Exception as e:
                logger.error(
                    f"Exception processing future dated membership id: {membership_id}: {e}"
                )
                errored += 1

        logger.info(
            f"Membership status update complete. {processed} processed, {errored} errored"
        )
