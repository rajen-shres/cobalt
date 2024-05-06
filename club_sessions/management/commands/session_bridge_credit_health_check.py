"""
Health Check for Duplicate Bridge Credit Payments in Club Sessions

Looks at all completed club session from a specified date
"""

from datetime import datetime, timedelta
import sys

from django.core.management.base import BaseCommand, CommandParser
from django.db.models import Sum, Subquery

from cobalt.settings import COBALT_HOSTNAME, MEDIA_ROOT, BRIDGE_CREDITS
from club_sessions.models import Session, SessionEntry, SessionMiscPayment
from accounts.models import User
from organisations.models import Organisation
from payments.models import OrgPaymentMethod, MemberTransaction


class Command(BaseCommand):
    help = "Health Check for duplicate Bridge Credit payments in club sessions"

    def add_arguments(self, parser):
        parser.add_argument("from", nargs=1, type=str, help="From date (dd-mm-yyyy)")

    def get_session_totals(self, club, session, club_bc_pm):
        """Return the relevant totals for the session:

        SessionEntry table money Bridge Credits (+ve)
        Session misc charges Bridge Credits (+ve)
        MemberTransaction session Bridge Credits payed (-ve)
        MemberTransaction refunds (+ve), matched using the description
        Discrepancy
        """

        # get a list of all Users who played in the session
        # (ie people who could have received a Bridge Credit refund)
        # playing_system_numbers = SessionEntry.objects.filter(session=session).values(
        #     "system_number",
        # )

        # playing_users = User.objects.filter(
        #     system_number__in=Subquery(playing_system_numbers)
        # )

        # calculate the total fees for the session, paid by Bridge Credits
        total_fee = SessionEntry.objects.filter(
            session=session, is_paid=True, payment_method=club_bc_pm
        ).aggregate(total=Sum("fee"))
        total_session_fees = total_fee.get("total", 0) if total_fee else 0
        total_session_fees = total_session_fees or 0

        # calculate the total misc payments for the session, paid by Bridge Credits
        total_misc = SessionMiscPayment.objects.filter(
            session_entry__session=session, payment_made=True, payment_method=club_bc_pm
        ).aggregate(total=Sum("amount"))
        total_session_misc = total_misc.get("total", 0) if total_misc else 0
        total_session_misc = total_session_misc or 0

        # calculate the amount accounted for in member transactions for the session
        total_payments = MemberTransaction.objects.filter(
            club_session_id=session.id,
        ).aggregate(total=Sum("amount"))
        total_session_payments = total_payments.get("total", 0) if total_payments else 0
        total_session_payments = total_session_payments or 0

        # calculate the amount refunded in member transactions with a description matching the session

        # but constrain to users in this session in case of duplicated session descriptions
        # total_refunds = MemberTransaction.objects.filter(
        #     description__startswith=f"Bridge Credits returned for {session.description}",
        #     member__in=playing_users,
        # ).aggregate(total=Sum("amount"))
        # total_session_refunds = total_refunds.get("total", 0) if total_refunds else 0
        # total_session_refunds = total_session_refunds or 0

        # but constrain to payments from this club in case of duplicated session descriptions
        # assumes that the transactions are on the same date as the session or within a few days
        total_refunds = MemberTransaction.objects.filter(
            description__startswith=f"Bridge Credits returned for {session.description}",
            created_date__date__gte=session.session_date,
            created_date__date__lte=session.session_date + timedelta(days=5),
            organisation=club,
        ).aggregate(total=Sum("amount"))
        total_session_refunds = total_refunds.get("total", 0) if total_refunds else 0
        total_session_refunds = total_session_refunds or 0

        discrepancy = (
            total_session_fees
            + total_session_misc
            + total_session_payments
            + total_session_refunds
        )

        return (
            total_session_fees,
            total_session_misc,
            total_session_payments,
            total_session_refunds,
            discrepancy,
        )

    def handle(self, *args, **options):
        self.stdout.write(
            "Health Check - Duplicate Bridge Credit Payments in Club Sessions"
        )

        try:
            from_date = datetime.strptime(options["from"][0], "%d-%m-%Y").date()
        except ValueError:
            self.stdout.write(f"Invalid from date format :{options['from']}")
            sys.exit()

        self.stdout.write(f"Sessions from {from_date.strftime('%d-%m-%Y')}")

        if COBALT_HOSTNAME == "127.0.0.1:8000":
            out_path = "/tmp/"
        else:
            out_path = MEDIA_ROOT + "/admin/"
        out_path += f"health-check-{datetime.now().strftime('%Y%m%d%H%M')}.csv"

        self.stdout.write(f"Writing to {out_path}")

        with open(out_path, "w") as out_file:

            out_file.write(
                "Health Check for Duplicate Bridge Credit Payments in Club Sessions\n"
            )
            out_file.write(f"Sessions from {from_date.strftime('%d-%m-%Y')}\n")
            out_file.write(
                "Session,Club,Director,Director Email,Fees Charged,Misc Charges,Payments,Refunds,Discrepancy,Direction\n"
            )

            # get all completed session in the date range
            sessions = Session.objects.filter(
                session_date__gte=from_date, status=Session.SessionStatus.COMPLETE
            ).order_by("session_date")

            candidate_count = sessions.count()

            self.stdout.write(f"{candidate_count} sessions to check")

            check_count = 0
            error_count = 0
            skip_count = 0

            for session in sessions:

                #  figure out which club this is associated with by looking at the session type
                club = session.session_type.organisation

                #  get the Bridge Credit payment method for this club
                bc_payment_type = OrgPaymentMethod.objects.filter(
                    active=True, organisation=club, payment_method="Bridge Credits"
                ).first()

                if bc_payment_type is None:
                    # club is not set-up for Bridge Credits
                    skip_count += 1
                    continue

                check_count += 1
                (
                    table_money,
                    misc,
                    payments,
                    refunds,
                    discrepancy,
                ) = self.get_session_totals(club, session, bc_payment_type)

                if discrepancy:
                    error_count += 1

                    # Too many false positives to flag them to the users :

                    # msg = (
                    #     f"ERROR: Expected {table_money + misc:.2f} {BRIDGE_CREDITS} payments, "
                    #     + f"{-discrepancy:.2f} {'overpayment' if discrepancy < 0 else 'underpayment'} found."
                    #     + " Please contact support."
                    # )
                    # add message to front of director's notes if not already there
                    # if session.director_notes:
                    #     if not session.director_notes.startswith("ERROR:"):
                    #         session.director_notes = (
                    #             f"{msg}\n\n{session.director_notes}"
                    #         )
                    #         session.save()
                    # else:
                    #     session.director_notes = msg
                    #     session.save()

                    log_line = (
                        f"{session} [{session.id}],{club} [{club.id}],{session.director.full_name},{session.director.email},"
                        + f"{table_money},{misc},{payments},{refunds},{discrepancy},"
                        + f"{'Overpayment' if discrepancy < 0 else 'Underpayment'}\n"
                    )
                    out_file.write(log_line)
                    self.stdout.write(log_line)

            out_file.write(
                f"{check_count} sessions checked with {skip_count} skipped and {error_count} errors found\n"
            )

        self.stdout.write(
            f"Complete: {check_count} sessions checked, {skip_count} skipped, {error_count} errors found"
        )
