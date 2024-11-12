"""
Bulk update of deceased players from a CSV file

The command takes a csv filename as an input

Row 1 is the system number of the person to be tagged as having updated the players
Subsequent rows each contain the system number of a deceased player (other columns ignored)
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from os import path
import sys
from accounts.models import User
from organisations.club_admin_core import mark_player_as_deceased


class Command(BaseCommand):
    help = "Bulk update of deceased players"

    def add_arguments(self, parser):
        parser.add_argument(
            "filename", nargs=1, type=str, help="The input csv file name"
        )

    def handle(self, *args, **options):
        self.stdout.write("Executing bulk_update_of_deceased")
        self.stdout.write("=================================\n")

        in_path = path.abspath(path.expandvars(path.expanduser(options["filename"][0])))
        self.stdout.write(f"Processing: {in_path}")

        with open(in_path, "r") as in_file:

            user = None
            first = True
            errors = 0
            successes = 0
            not_found = 0

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

                    self.stdout.write(f"Updates by {user}/n")

                else:
                    # process a member row

                    try:
                        deceased_system_number = int(csv_fields[0])
                    except ValueError:
                        self.stdout.write(
                            f"Error: first value must be an integer system number, '{clean_row}'"
                        )
                        errors += 1
                        continue

                    with transaction.atomic():
                        success = mark_player_as_deceased(deceased_system_number, user)

                        if success:
                            successes += 1
                            self.stdout.write(f"Done, {clean_row}")

                        else:
                            not_found += 1
                            self.stdout.write(f"Not found, {clean_row}")

        self.stdout.write(
            f"\nFinished: {errors} errors, {successes} updated successfully, {not_found} not found.\n"
        )
