"""
Batch command to update time sensitive membership statuses

Should be run nightly soon after midnight via cron
Can be run at any time manually with an optional date arguement
"""

from datetime import datetime, timedelta
import logging
import sys

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
    MEMBERSHIP_STATES_ACTIVE,
)

logger = logging.getLogger("cobalt")


class Command(BaseCommand):
    help = "Periodic batch command to update time sensitive membership statuses"

    def add_arguments(self, parser):
        # Add an optional '--date' argument
        parser.add_argument(
            "--date",
            type=str,  # Argument type
            help="Optional date in the format YYYY-MM-DD",
        )

    def get_club(self, club_id):
        """Cached lookup of club"""
        if club_id not in self.club_cache:
            club = Organisation.objects.get(pk=club_id)
            self.club_cache[club_id] = club
        return self.club_cache[club_id]

    def lapse(self, club, system_number):
        """Lapse a membership"""

        try:
            lapsed_ok, lapse_msg = perform_simple_action("lapsed", club, system_number)
        except Exception as e:
            lapsed_ok = False
            lapse_msg = f"Exception {e}"

        if lapsed_ok:
            self.processed += 1
        else:
            logger.warning(f"Error lapsing {system_number}: {lapse_msg}")
            self.errored += 1

        return lapsed_ok

    def transition_to_future(
        self, new_state, member_details, this_membership, future_membership
    ):
        """Transition to a future membership with a specified state"""

        this_membership.membership_state = MemberMembershipType.MEMBERSHIP_STATE_ENDED
        this_membership.save()

        future_membership.membership_state = new_state
        future_membership.save()

        member_details.latest_membership = future_membership
        member_details.membership_status = new_state
        member_details.save()

        self.processed += 1

    def handle(self, *args, **options):

        # Get the optional date argument
        date_str = options.get("date")

        if date_str:
            try:
                today = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                logger.error(f"Invalid date arguement '{date_str}'. Use YYYY-MM-DD.")
                sys.exit()
        else:
            # today = timezone.now().date()
            today = timezone.localtime().date()
        yesterday = today - timedelta(days=1)

        logger.info(f"Membership status update starting for {today}")

        self.processed = 0
        self.errored = 0
        self.skipped = 0
        self.club_cache = {}

        # get unpaid memberships at their due date

        at_due_membership_list = (
            MemberMembershipType.objects.filter(
                membership_type__organisation__full_club_admin=True,
                due_date=yesterday,
            )
            .exclude(
                fee=0,
                is_paid=True,
            )
            .values_list("id", "membership_type__organisation__id", "system_number")
        )

        logger.info(
            f"Starting due date processing: {len(at_due_membership_list)} found"
        )

        for membership_id, club_id, system_number in at_due_membership_list:
            with transaction.atomic():

                club = self.get_club(club_id)
                this_membership = MemberMembershipType.objects.get(id=membership_id)

                member_details = (
                    MemberClubDetails.objects.filter(
                        club=club,
                        system_number=system_number,
                    )
                    .select_related("latest_membership")
                    .last()
                )

                # JPG debug
                # print(f"due: {system_number}, {club}")

                if member_details.latest_membership == this_membership:
                    # the due date is within the current membership
                    # (scenario 3 - not paid at due date)

                    lapsed_ok = self.lapse(club, system_number)

                    # curtail the membership
                    if lapsed_ok:
                        this_membership = MemberMembershipType.objects.get(
                            id=membership_id
                        )
                        this_membership.end_date = yesterday
                        this_membership.save()

                else:
                    # alternative is that the due date is for a future membership
                    # (scenario 2) and no action is required.
                    self.skipped += 1

        logger.info(
            f"Finished due date processing: {self.processed} ok, "
            + f"{self.errored} errored, {self.skipped} no action required"
        )

        # get memberships at their end date

        at_end_membership_list = MemberMembershipType.objects.filter(
            membership_type__organisation__full_club_admin=True,
            end_date=yesterday,
            membership_state__in=MEMBERSHIP_STATES_ACTIVE,
        ).values_list("id", "membership_type__organisation__id", "system_number")

        logger.info(
            f"Starting end date processing: {len(at_end_membership_list)} found"
        )

        for membership_id, club_id, system_number in at_end_membership_list:
            with transaction.atomic():

                club = self.get_club(club_id)
                this_membership = MemberMembershipType.objects.get(id=membership_id)

                member_details = (
                    MemberClubDetails.objects.filter(
                        club=club,
                        system_number=system_number,
                    )
                    .select_related("latest_membership")
                    .last()
                )

                future_membership = MemberMembershipType.objects.filter(
                    membership_type__organisation=club,
                    system_number=system_number,
                    membership_state=MemberMembershipType.MEMBERSHIP_STATE_FUTURE,
                ).last()

                # JPG debug
                # print(f"end: {system_number}, {club}, {'FUT' if future_membership else '-'}")

                if future_membership:

                    if future_membership.start_date != today:
                        # invalid data state
                        logger.error(
                            f"Error on {system_number} at {club}:"
                            + f"invalid start ({future_membership.start_date}) on future membership"
                        )
                        self.errored += 1
                        continue

                    if future_membership.is_paid:
                        # just need to transition to the future paid membership

                        self.transition_to_future(
                            MemberMembershipType.MEMBERSHIP_STATE_CURRENT,
                            member_details,
                            this_membership,
                            future_membership,
                        )

                    else:
                        if future_membership.due_date < today:
                            # overdue so lapse the ending membership and delete the future

                            self.lapse(club, system_number)

                        else:
                            # still have time to pay, so make it due

                            self.transition_to_future(
                                MemberMembershipType.MEMBERSHIP_STATE_DUE,
                                member_details,
                                this_membership,
                                future_membership,
                            )
                else:
                    # reached end date, no future (secnario 1), lapse

                    self.lapse(club, system_number)

        logger.info(
            f"Membership status update complete. {self.processed} processed, "
            + f"{self.errored} errored {self.skipped} no action required"
        )
