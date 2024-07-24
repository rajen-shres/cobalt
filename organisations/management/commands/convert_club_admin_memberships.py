"""
Data conversion of club memberships for full club admin (release 6).

A script to perform one off data conversion for existing club members after the
migration to the full club admin data model (in Release 6).

All of the work is performed by functions from club_admin_core.py
"""

from django.core.management.base import BaseCommand

from organisations.club_admin_core import convert_existing_memberships_for_club
from organisations.models import Organisation


class Command(BaseCommand):
    help = "Data conversion of club memberships for full club admin (release 6)."

    def handle(self, *args, **options):

        self.stdout.write("Executing convert_club_admin_memberships.py\n")

        total_ok = 0
        total_error = 0
        clubs_ok = 0
        clubs_errored = 0
        clubs_skipped = 0

        clubs = Organisation.objects.all()

        for club in clubs:
            ok_count, error_count = convert_existing_memberships_for_club(club)
            if ok_count + error_count > 0:
                if error_count == 0:
                    clubs_ok += 1
                    self.stdout.write(f"{club.name:50} {ok_count} OK")
                else:
                    clubs_errored += 1
                    self.stdout.write(
                        f"{club.name:50} {ok_count} OK, {error_count} ERRORS"
                    )
                total_ok += ok_count
                total_error += error_count
            else:
                clubs_skipped += 1
                self.stdout.write(f"{club.name:50} Skipped (no members)")

        self.stdout.write("\nconvert_club_admin_memberships.py complete")
        if total_error == 0:
            self.stdout.write(
                f"No issues found, {total_ok} members converted in {clubs_ok} clubs\n"
            )
        else:
            self.stdout.write(
                f"Unable to convert {total_error} members, impacting {clubs_errored} clubs"
            )
            self.stdout.write(
                "See cobalt.log for details (grep convert_existing_memberships_for_club)"
            )
            self.stdout.write(
                f"{total_ok} members converted. {clubs_ok} clubs had no errors\n"
            )
