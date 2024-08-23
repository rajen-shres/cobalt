"""
Bulk removal of club members

The input is a csv file. Row 1 identifies the club and a administrator,
all subsequent rows are pairs of abf number and name (not used in matching).

The script can be run in two modes - report only or update. In report only
mode no database updates are made, but the output file is created to document
what would have happened if the script had been run in update mode.

The command takes a csv filename as an input, with an optional --update parameter.
If update is not specified the mode defaults to report only.

Output is to a csv file with the same name as the input file, but with '-log'
added to the file name (eg if the input file is "TBA-member-removal-240104.csv",
the log file is "TBA-member-removal-240104-log.csv"). The output is a copy of the
imput data with up to two fields appended to the member rows, a status flag
('Y' = processed, 'E' = errored, 'U' = unregistered user) and an error message.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from os import path

from cobalt.settings import (
    GLOBAL_CURRENCY_SYMBOL,
    BRIDGE_CREDITS,
)
from accounts.models import (
    UnregisteredUser,
    User,
)
from organisations.models import (
    ClubLog,
    ClubMemberLog,
    MemberClubTag,
    MemberClubEmail,
    MemberClubDetails,
    MemberMembershipType,
    Organisation,
)


RESULT_ERROR = "Error"
RESULT_PROCESSED = "Removed"


class Command(BaseCommand):
    help = "Bulk removal of club members"

    def add_arguments(self, parser):
        parser.add_argument(
            "filename", nargs=1, type=str, help="The input csv file name"
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Run in update mode (otherwise report only)",
        )

    def process_club_row(self, row):
        """
        Process the first non-blank, non-comment row as specifying a club
        and requesting user (both required).
        Saves the club and requesing user if found, otherwise sets to None
        Returns (success, error message or None)
        """
        self.club = None
        self.requestor = None
        csv_fields = row.split(",")
        if len(csv_fields) < 2:
            return (False, "Malformed row, club and requestor required")

        club_query = Organisation.objects.filter(org_id=csv_fields[0])
        if not club_query.exists():
            return (False, f"Club '{csv_fields[0]}' not found")
        self.club = club_query.get()

        try:
            requestor_number = int(csv_fields[1])
        except ValueError:
            return (False, f"Invalid requestor number '{csv_fields[1]}'")

        user_query = User.objects.filter(system_number=requestor_number)
        if not user_query.exists():
            self.requestor = None
            return (False, f"Requestor '{requestor_number}' not found")
        self.requestor = user_query.get()

        return (True, None)

    def cancel_membership(self, system_number):
        """
        Cancel a membership - based on the common routine _cancel_membership
        Requires club and requestor to be set
        Returns an result code and error message (or None)
        """

        try:
            with transaction.atomic():

                # start with the membership details
                member_details_count = MemberClubDetails.objects.filter(
                    club=self.club,
                    system_number=system_number,
                ).count()

                if member_details_count == 0:
                    return (RESULT_ERROR, "Not a member")

                # should be only one, but delete any to be thorough
                member_details_count = MemberClubDetails.objects.filter(
                    club=self.club,
                    system_number=system_number,
                ).delete()

                ClubLog(
                    organisation=self.club,
                    actor=self.requestor,
                    action=f"Deleted membership for {system_number}",
                ).save()

                # delete any membership records
                MemberMembershipType.objects.filter(
                    system_number=system_number, membership_type__organisation=self.club
                ).delete()

                # Delete any tags
                MemberClubTag.objects.filter(club_tag__organisation=self.club).filter(
                    system_number=system_number
                ).delete()

                # Delete any club member log records
                ClubMemberLog.objects.filter(
                    club=self.club,
                    system_number=system_number,
                ).delete()

                # Remove any email addresses for this club and user (left over from pre club admin)
                MemberClubEmail.objects.filter(
                    organisation=self.club, system_number=system_number
                ).delete()

                # check for an unregistered user with an internal system number
                # and delete it if found (only if called for a contact)
                check_unreg = UnregisteredUser.all_objects.filter(
                    system_number=system_number,
                ).last()

                if check_unreg and check_unreg.internal_system_number:
                    check_unreg.delete()

        except Exception as e:
            return (RESULT_ERROR, f"{e}")

        return (RESULT_PROCESSED, None)

    def process_user_row(self, row):
        """
        Process a non-blank, non-comment row as specifying a member
        Returns a result code and an error message (or None)
        """
        csv_fields = row.split(",")

        if len(csv_fields) < 2:
            return (RESULT_ERROR, "Malformed row, at least 2 columns required")

        try:
            this_system_number = int(csv_fields[0])
        except ValueError:
            return (RESULT_ERROR, "Malformed user number")

        # Bug fix: non-registered users can be club members
        # user_query = User.objects.filter(system_number=this_system_number)
        # if not user_query.exists():
        #     return (RESULT_ERROR, "User not registered")

        if not self.make_updates:
            if (
                MemberMembershipType.objects.filter(system_number=this_system_number)
                .filter(membership_type__organisation=self.club)
                .exists()
            ):
                return (RESULT_PROCESSED, None)
            else:
                return (RESULT_ERROR, "Not a member")
        else:
            return self.cancel_membership(this_system_number)

    def handle(self, *args, **options):
        self.stdout.write("Executing remove_club_membership")

        self.make_updates = options["update"]

        self.stdout.write(
            f"Running in {'UPDATE' if self.make_updates else 'report only'} mode"
        )

        in_path = path.abspath(path.expandvars(path.expanduser(options["filename"][0])))
        (root, ext) = path.splitext(in_path)
        out_path = root + "-log" + ext

        self.stdout.write(f"Processing: {in_path}")
        self.stdout.write(f"Logging to: {out_path}")

        with open(in_path, "r") as in_file, open(out_path, "w") as out_file:
            self.club = None
            self.requestor = None
            abort = False
            users_read = 0
            users_processed = 0
            users_errored = 0
            for row in in_file:
                clean_row = row.strip()

                if len(clean_row) == 0 or clean_row[:1] == "#" or abort:
                    # ignore the row
                    out_file.write(row)

                elif self.club is None:
                    row_ok, error_msg = self.process_club_row(row)
                    if not row_ok:
                        # cannot continue without a valid club
                        self.stdout.write(f"Aborting - {error_msg}")
                        abort = True
                        out_file.write(f"{clean_row}, Aborting - {error_msg}\n")
                    else:
                        self.stdout.write(f"Club = {self.club}")
                        self.stdout.write(f"Requestor = {self.requestor}")
                        out_file.write(f"{clean_row}\n")

                else:
                    users_read += 1
                    result_code, msg = self.process_user_row(row)
                    if result_code == RESULT_PROCESSED:
                        users_processed += 1
                        out_file.write(f"{clean_row},{RESULT_PROCESSED}\n")

                    elif result_code == RESULT_ERROR:
                        users_errored += 1
                        out_file.write(
                            f"{clean_row},{RESULT_ERROR},{msg if msg is not None else 'Error processing removal'}\n"
                        )

                    else:
                        users_errored += 1
                        out_file.write(
                            f"{clean_row},{RESULT_ERROR},{msg if msg is not None else 'Unknown error'}\n"
                        )

            out_file.write("\n")
            out_file.write(f"{'#' * 80}\n")
            out_file.write("#\n")
            if not self.make_updates:
                out_file.write(
                    "#   *** RUNNING IN REPORT ONLY MODE *** No database updates made\n"
                )
                out_file.write("#\n")
            if abort:
                out_file.write("#   Processing aborted, invalid club or requestor\n")
                print("*** Run aborted - check the log ***")
            else:
                out_file.write(f"#   Club: {self.club}\n")
                out_file.write(f"#   Requestor: {self.requestor}\n")
                out_file.write("#\n")
                out_file.write(
                    f"#   User records read                 : {users_read}\n"
                )
                out_file.write(
                    f"#   Members removed                   : {users_processed}\n"
                )
                out_file.write(
                    f"#   Users not removed due to error    : {users_errored}\n"
                )
            out_file.write("#\n")
            out_file.write(f"{'#' * 80}\n")

            if users_errored > 0:
                print(f"*** Completed with {users_errored} errors - check the log *** ")
            else:
                print("Completed - no errors")
