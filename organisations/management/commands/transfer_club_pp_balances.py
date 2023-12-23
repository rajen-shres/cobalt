"""
Bulk transfer of club prepayment account balances to bridge credits.

A script to perform once off transfers of bridge credits from a club account
to member accounts to reflect the members balance in their club prepayment
system.

The input is a csv file. Row 1 identifies the club and a administrator,
all subsequent rows are triplets of abf number, name (not used in matching)
and account balance.

The script can be run in two modes - report only or update. In report only
mode no database updates are made and no emails sent, but the output file
is created to document what would have happened if the script had been run
in update mode.

The command takes a csv filename as an input, with an optional --update parameter.
If update is not specified the mode defaults to report only.

Output is to a csv file with the same name as the input file, but with '-log'
added to the file name (eg if the input file is "TBA-pp-balances-231220.csv",
the log file is "TBA-pp-balances-231220-log.csv"). The output is a copy of the
imput data with up to two fields appended to the balance rows, a status flag
('Y' = processed, 'E' = errored, 'U' = unregistered user) and an error message.
"""

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction
from os import path

from cobalt.settings import GLOBAL_CURRENCY_SYMBOL, BRIDGE_CREDITS

from organisations.models import ClubLog, Organisation
from accounts.models import User
from notifications.views.core import send_cobalt_email_to_system_number
from payments.views.core import update_account, update_organisation

# DATA_DIR = "tests/test_data"

RESULT_ERROR = "Error"
RESULT_PROCESSED = "Processed"
RESULT_NOT_REGISTERED = "Not registered"


class Command(BaseCommand):
    help = "Bulk transfer of club prepayment account balances to bridge credits"

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

        # TO DO - should check RBAC for requestor
        return (True, None)

    def do_transfer(self, member, pp_balance):
        """
        Do the transfer, debiting the club, crediting the member and sending an email to the member
        Returns success.
        Should only be called in update mode
        """
        description = "Transfer of club pre-payment account balance"

        with transaction.atomic():
            # Perform the databse updates as a single LUW

            # Credit user
            update_account(
                member=member,
                amount=pp_balance,
                description=description,
                organisation=self.club,
                payment_type="Org Transfer",
            )

            # Debit club
            update_organisation(
                organisation=self.club,
                amount=-pp_balance,
                description=description,
                payment_type="Org Transfer",
                member=member,
            )

            # log it
            ClubLog(
                organisation=self.club,
                actor=self.requestor,
                action=f"Paid {GLOBAL_CURRENCY_SYMBOL}{pp_balance:,.2f} to {member}",
            ).save()

        # notify user
        msg = f"""{self.club} (administrator {self.requestor}) has paid {GLOBAL_CURRENCY_SYMBOL}{pp_balance:,.2f} to your {BRIDGE_CREDITS}
        account for {description}.
            <br><br>If you have any queries please contact {self.club} in the first instance.
        """
        send_cobalt_email_to_system_number(
            system_number=member.system_number,
            subject=f"Payment from {self.club}",
            message=msg,
            club=self.club,
        )

        # TO DO - data integrity across LUW
        return True

    def process_user_row(self, row):
        """
        Process a non-blank, non-comment row as specifying a user balance
        Returns a result code, the balance amount (or None) and an error message (or None)
        """
        csv_fields = row.split(",")

        if len(csv_fields) < 3:
            return (RESULT_ERROR, None, "Malformed row, at least 3 columns required")

        try:
            this_system_number = int(csv_fields[0])
        except ValueError:
            return (RESULT_ERROR, None, "Malformed user number")

        user_query = User.objects.filter(system_number=this_system_number)
        if not user_query.exists():
            return (RESULT_NOT_REGISTERED, None, "User not registered")

        try:
            pp_balance = float(csv_fields[2])
        except ValueError:
            return (RESULT_ERROR, None, "Error reading balance")

        if pp_balance != float(int(pp_balance * 100) / 100):
            return (RESULT_ERROR, None, "Invalid balance, fractional cents")

        if pp_balance == 0:
            return (RESULT_PROCESSED, 0, None)

        if pp_balance < 0:
            return (RESULT_ERROR, None, "Club prepayment account is in debt")

        if not self.make_updates:
            return (RESULT_PROCESSED, pp_balance, None)

        if self.do_transfer(user_query.get(), pp_balance):
            return (RESULT_PROCESSED, pp_balance, None)
        else:
            return (RESULT_ERROR, None, "An error occurred posting the updates")

    def handle(self, *args, **options):
        self.stdout.write("Executing transfer_club_pp_balances")

        self.make_updates = options["update"]

        self.stdout.write(
            f"Running in {'UPDATE' if self.make_updates else 'report only'} mode"
        )

        # in_path = path.join(DATA_DIR, options['filename'][0])
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
            users_not_registered = 0
            users_errored = 0
            total_transferred = 0
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
                    result_code, balance, msg = self.process_user_row(row)
                    if result_code == RESULT_PROCESSED:
                        users_processed += 1
                        total_transferred += balance
                        out_file.write(f"{clean_row},{RESULT_PROCESSED}\n")

                    elif result_code == RESULT_NOT_REGISTERED:
                        users_not_registered += 1
                        out_file.write(
                            f"{clean_row},{RESULT_NOT_REGISTERED},{msg if msg is not None else 'User not registered'}\n"
                        )

                    elif result_code == RESULT_ERROR:
                        users_errored += 1
                        out_file.write(
                            f"{clean_row},{RESULT_ERROR},{msg if msg is not None else 'Error processing transfer'}\n"
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
                    "#   *** RUNNING IN REPOPT ONLY MODE *** No database updates made\n"
                )
                out_file.write("#\n")
            if abort:
                out_file.write("#   Processing aborted, invalid club or requestor\n")
            else:
                out_file.write(f"#   Club: {self.club}\n")
                out_file.write(f"#   Requestor: {self.requestor}\n")
                out_file.write("#\n")
                out_file.write(
                    f"#   User records read                 : {users_read}\n"
                )
                out_file.write(
                    f"#   Balances transferred              : {users_processed}\n"
                )
                out_file.write(
                    f"#   Users not registered with MyABF   : {users_not_registered}\n"
                )
                out_file.write(
                    f"#   Users not transfered due to error : {users_errored}\n"
                )
                out_file.write("#\n")
                out_file.write(
                    f"#   Total balance transferred         : ${total_transferred:,.2f}\n"
                )
            out_file.write("#\n")
            out_file.write(f"{'#' * 80}\n")
