"""
Health Check for Duplicate Bridge Credit Payments in Club Sessions

Looks at all completed club session from a specified date
"""

from datetime import datetime
import sys

from django.core.management.base import BaseCommand, CommandParser
from django.db.models import Sum

from cobalt.settings import COBALT_HOSTNAME, MEDIA_ROOT
from club_sessions.models import Session, SessionEntry
from club_sessions.views.manage_session import _session_health_check
from organisations.models import Organisation
from payments.models import OrgPaymentMethod


class Command(BaseCommand):
    help = "Health Check for duplicate Bridge Credit payments in club sessions"

    def add_arguments(self, parser):
        parser.add_argument("from", nargs=1, type=str, help="From date (dd-mm-yyyy)")

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
        out_path += f"health-check-{datetime.now().strftime('%Y%m%d%H%M')}.txt"

        self.stdout.write(f"Writing to {out_path}")

        with open(out_path, "w") as out_file:

            out_file.write(
                "Health Check for Duplicate Bridge Credit Payments in Club Sessions\n"
            )
            out_file.write(f"Sessions from {from_date.strftime('%d-%m-%Y')}\n\n")

            # get all comppleted session in the date range
            sessions = Session.objects.filter(
                session_date__gte=from_date, status=Session.SessionStatus.COMPLETE
            )

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
                msg = _session_health_check(club, session, bc_payment_type, None)
                msg = "test payload"

                if msg:
                    error_count += 1
                    out_file.write(
                        f"Session: {session}, club: {club}, director: {session.director.full_name} ({session.director.email})\n"
                    )
                    out_file.write(f"    {msg}\n\n")
                    self.stdout.write(f"   {session} [{session.id}]")
                    self.stdout.write(f"      {msg}")

            out_file.write(
                f"{check_count} sessions checked, {skip_count} skipped, {error_count} errors found"
            )

        self.stdout.write(
            f"Complete: {check_count} sessions checked, {skip_count} skipped, {error_count} errors found"
        )
