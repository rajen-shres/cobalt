"""
Batch command to update time sensitive membership statuses

Should be run nightly soon after midnight via cron
Can be run at any time manually with an optional date arguement

WARNING - The data parameter should not be used in production.
This script will honour that date, but it calls the core lapse
function which uses the real date.
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
    log_member_change,
    perform_simple_action,
    MEMBERSHIP_STATES_ACTIVE,
    MEMBERSHIP_STATES_TERMINAL,
    CobaltMemberNotFound,
)
from utils.views.cobalt_lock import CobaltLock


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

    def lapse(self, club, system_number, scenario_str=None, fatal=True):
        """Lapse a membership
        fatal indicates whether failure to lapse is an error or a warning"""

        try:
            lapsed_ok, lapse_msg = perform_simple_action("lapsed", club, system_number)
        except CobaltMemberNotFound as e:
            logger.error(f"Exception while lapsing: {e}")
            self.errored += 1
            raise

        if lapsed_ok:
            self.processed += 1
        else:
            if fatal:
                logger.error(
                    f"{system_number} {scenario_str if scenario_str else ''} "
                    + f"Error lapsing : {lapse_msg}"
                )
                self.errored += 1
            else:
                logger.warning(
                    f"{system_number} {scenario_str if scenario_str else ''} "
                    + f"Error lapsing : {lapse_msg}"
                )
                self.processed += 1

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

        log_member_change(
            member_details.club,
            member_details.system_number,
            None,
            (
                f"Transitioned to {future_membership.membership_type.name} "
                + f" {future_membership.get_membership_state_display()}"
            ),
        )

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

        # Use a logical lock to ensure that processes are not running on
        # multiple servers. If another job is running simply exit
        ums_lock = CobaltLock("update_membership_status", expiry=10)
        if not ums_lock.get_lock():
            logger.info(
                "Update membership status already ran or running (locked), exiting"
            )
            sys.exit(0)

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
            .exclude(fee=0)
            .exclude(is_paid=True)
            .exclude(membership_state__in=MEMBERSHIP_STATES_TERMINAL)
            .values_list("id", "membership_type__organisation__id", "system_number")
        )

        if len(at_due_membership_list):
            logger.info(
                f"Starting {yesterday} due date processing: {len(at_due_membership_list)} found"
            )
        else:
            logger.info(f"No memberships with due date {yesterday} to process")

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

                if member_details.latest_membership == this_membership:
                    # the due date is within the current membership
                    # (scenario 3.2.1 - not paid at due date)

                    try:
                        lapsed_ok = self.lapse(
                            club,
                            system_number,
                            scenario_str="[Scenario 3.2.1]",
                            fatal=False,
                        )
                    except CobaltMemberNotFound:
                        #  lapse will have logged the exception, but can't keep going
                        continue

                    # the only error condition preventing lapsing would be already inactive
                    # in which case we can continue anyway

                    # curtail the membership
                    this_membership = MemberMembershipType.objects.get(id=membership_id)
                    if (
                        not this_membership.end_date
                        or this_membership.end_date > yesterday
                    ):
                        this_membership.end_date = yesterday
                        this_membership.save()

                    logger.info(
                        f"{member_details.system_number} [Scenario 3.2.1] lapsed and curtailed"
                    )

                else:
                    # alternative is that the due date is for a future membership
                    # (scenario 2.1) and no action is required.
                    logger.info(
                        f"{member_details.system_number} [Scenario 2.1] no action required"
                    )
                    self.skipped += 1

        if len(at_due_membership_list):
            logger.info(
                f"Finished due date processing: {self.processed} ok, "
                + f"{self.errored} errored, {self.skipped} no action required"
            )

        self.due_processed = self.processed
        self.due_errored = self.errored
        self.due_skipped = self.skipped
        self.processed = 0
        self.errored = 0
        self.skipped = 0

        # get memberships at their end date

        at_end_membership_list = MemberMembershipType.objects.filter(
            membership_type__organisation__full_club_admin=True,
            end_date=yesterday,
            membership_state__in=MEMBERSHIP_STATES_ACTIVE,
        ).values_list("id", "membership_type__organisation__id", "system_number")

        if len(at_end_membership_list):
            logger.info(
                f"Starting {yesterday} end date processing: {len(at_end_membership_list)} found"
            )
        else:
            logger.info(f"No memberships with end date {yesterday} to process")

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

                if future_membership:

                    if (
                        not future_membership.start_date
                        or future_membership.start_date != today
                    ):
                        # invalid data state
                        logger.error(
                            f"Error on {system_number} at {club}:"
                            + f"invalid start ({future_membership.start_date}) on future membership"
                        )
                        self.errored += 1
                        continue

                    if future_membership.is_paid:
                        # just need to transition to the future paid membership
                        # scenario 2.2.1 or 3.1.1

                        if future_membership.due_date:
                            if (
                                future_membership.due_date
                                >= future_membership.start_date
                            ):
                                scenario = "Scenario 3.1.1"
                            else:
                                scenario = "Scenario 2.2.1"
                        else:
                            scenario = "No due date"

                        self.transition_to_future(
                            MemberMembershipType.MEMBERSHIP_STATE_CURRENT,
                            member_details,
                            this_membership,
                            future_membership,
                        )

                        logger.info(
                            f"{member_details.system_number} [{scenario}] transition to renewal"
                        )

                    else:
                        if (
                            future_membership.due_date
                            and future_membership.due_date < today
                        ):
                            # overdue so lapse the ending membership and delete the future
                            # scenario 2.2.2

                            try:
                                lapsed_ok = self.lapse(
                                    club,
                                    system_number,
                                    scenario_str="[Scenario 2.2.2]",
                                    fatal=False,
                                )
                            except CobaltMemberNotFound:
                                #  lapse will have logged the exception, but can't keep going
                                continue

                            # only failure condition is already inactive, in which
                            # case we still need to delete the future membership
                            # this would be an anomaly as lapsing etc would have deleted any future
                            if not lapsed_ok:
                                future_membership.delete()

                            logger.info(
                                f"{member_details.system_number} [Scenario 2.2.2] membership lapsed"
                            )

                        else:
                            # still have time to pay, so make it due (scenario 3.1.2)
                            # including no due date case

                            self.transition_to_future(
                                MemberMembershipType.MEMBERSHIP_STATE_DUE,
                                member_details,
                                this_membership,
                                future_membership,
                            )

                            if future_membership.due_date:
                                logger.info(
                                    f"{member_details.system_number} "
                                    + "[Scenario 3.1.2] transition to due renewal"
                                )
                            else:
                                logger.warning(
                                    f"{member_details.system_number} "
                                    + "[Scenario 3.1.2] transition to due renewal but NO DUE DATE SET"
                                )

                else:
                    # reached end date, no future (scenario 1), lapse

                    try:
                        lapsed_ok = self.lapse(
                            club,
                            system_number,
                            scenario_str="[Scenario 1]",
                            fatal=False,
                        )
                    except CobaltMemberNotFound:
                        #  lapse will have logged the exception, but can't keep going
                        continue

                    if lapsed_ok:
                        logger.info(
                            f"{member_details.system_number} "
                            + "[Scenario 1] membership lapsed"
                        )

        if len(at_end_membership_list):
            logger.info(
                f"Finished end date processing: {self.processed} ok, "
                + f"{self.errored} errored, {self.skipped} no action required"
            )

        # release the lock
        # ums_lock.free_lock()
        # ums_lock.delete_lock()

        logger.info(
            "Membership status update complete. "
            + f"{self.processed + self.due_processed} processed, "
            + f"{self.errored + self.due_errored} errored "
            + f"{self.skipped + self.due_skipped} no action required"
        )
