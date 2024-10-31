"""
Bulk upload of club membership year start dates from a CSV file

This is to be run once as part of teh Release 6.0 deployment

The command takes a csv filename as an input

Row 1 is the system number of the person to be tagged as having updated the clubs
Subsequent rows contain:
    club org_id
    day
    month
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from os import path
import sys
from accounts.models import User
from organisations.models import Organisation


class Command(BaseCommand):
    help = "Bulk upload of club membership year start dates"

    def add_arguments(self, parser):
        parser.add_argument(
            "filename", nargs=1, type=str, help="The input csv file name"
        )

    def handle(self, *args, **options):
        self.stdout.write("Executing upload_club_membership_year")

        in_path = path.abspath(path.expandvars(path.expanduser(options["filename"][0])))
        self.stdout.write(f"Processing: {in_path}")

        with open(in_path, "r") as in_file:

            user = None
            first = True
            errors = 0
            successes = 0

            for row in in_file:
                clean_row = row.strip().replace("\ufeff", "")

                comment_marker = "#"

                if (
                    len(clean_row) == 0
                    or clean_row.startswith(comment_marker)
                    or clean_row == ",,"
                ):
                    # ignore the row
                    continue

                csv_fields = clean_row.split(",")

                if first:
                    # need a valid system number in the first row
                    try:
                        user_system_number = int(csv_fields[0])
                    except ValueError:
                        self.stdout.write(
                            "Error: first non-blank, non-comment row must be a valid user system number"
                        )
                        self.stdout.write(f"Error: '{clean_row}'")
                        sys.exit(1)
                    try:
                        user = User.objects.get(system_number=user_system_number)
                    except User.DoesNotExist:
                        self.stdout.write(
                            "Error: first non-blank, non-comment row must be a valid user system number"
                        )
                        self.stdout.write(f"Error: '{clean_row}'")
                        sys.exit(1)
                    first = False

                    self.stdout.write(f"Updates by {user}")

                else:
                    # process a club row
                    if len(csv_fields) < 3:
                        self.stdout.write(
                            f"Error: invalid row, 3 values required '{clean_row}'"
                        )
                        errors += 1
                        continue

                    club_org_id = csv_fields[0]
                    try:
                        start_day = int(csv_fields[1])
                        start_month = int(csv_fields[2])
                    except ValueError:
                        self.stdout.write(f"Error: invalid numeric value '{clean_row}'")
                        errors += 1
                        continue
                    if start_day < 1 or start_day > 31:
                        self.stdout.write(f"Error: invalid start day '{start_day}'")
                        errors += 1
                        continue
                    if start_month < 1 or start_month > 12:
                        self.stdout.write(f"Error: invalid start month '{start_month}'")
                        errors += 1
                        continue

                    try:
                        club = Organisation.objects.get(org_id=club_org_id)
                    except Organisation.DoesNotExist:
                        self.stdout.write(f"Error: invalid club org_id '{club_org_id}'")
                        errors += 1
                        continue

                    club.membership_renewal_date_day = start_day
                    club.membership_renewal_date_month = start_month
                    club.last_updated_by = user
                    club.save()

                    self.stdout.write(
                        f"{club_org_id} {club.name} updated: {start_day}/{start_month}"
                    )
                    successes += 1

        self.stdout.write(
            f"Finished: {errors} errors, {successes} updated successfully."
        )
