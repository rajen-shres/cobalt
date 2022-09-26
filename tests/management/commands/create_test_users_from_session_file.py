import re
from random import randint

from django.core.exceptions import SuspiciousOperation
from django.core.management.base import BaseCommand

from accounts.models import User
from cobalt.settings import COBALT_HOSTNAME
from organisations.models import Organisation, MembershipType, MemberMembershipType
from payments.views.core import update_account


def make_data(system_number, first_name, last_name, club, membership):
    """create user and associated records"""

    # create user
    user = User.objects.filter(system_number=system_number).first()

    if not user:
        user = User.objects.create_user(
            username=system_number,
            email="success@simulator.amazonses.com",
            password="F1shcake",
            first_name=first_name,
            last_name=last_name,
            system_number=system_number,
            about="",
        )
        user.save()
        print(f"Created used - {user}")
    else:
        print(f"User already existed - {user}")

    # Set balance
    amount = randint(0, 100)
    update_account(
        member=user,
        amount=amount,
        description="Set up balance",
        organisation=club,
        payment_type="Miscellaneous",
    )

    # Add most but not all as members
    if randint(0, 10) != 5:
        MemberMembershipType(
            membership_type=membership,
            system_number=system_number,
            last_modified_by=user,
        ).save()

    # Set some to be auto top up (won't actually work but will look they are set up)
    if randint(0, 10) > 3:
        user.stripe_auto_confirmed = True
        user.save()


class Command(BaseCommand):
    """
    Reads a compscore user file and creates the users, so we can test club_sessions
    """

    def add_arguments(self, parser):
        parser.add_argument("cs2_file", type=str)
        parser.add_argument(
            "club_pk",
            type=int,
            help="primary key for club you are testing with. Used to add members.",
        )

    def handle(self, *args, **options):

        if COBALT_HOSTNAME in ["myabf.com.au", "www.myabf.com.au"]:
            raise SuspiciousOperation(
                "Not for use in production. This cannot be used in a production system."
            )

        cs2_file = options["cs2_file"]
        club_pk = options["club_pk"]
        club = Organisation.objects.get(pk=club_pk)
        membership = MembershipType.objects.filter(organisation=club).first()

        with open(cs2_file) as file:
            for line in file:
                d = re.match(
                    r"(\d+)\s+(\w+)\s+(\w+)\s+/\s+(\w+)\s+(\w+)\s+\((\d+)\s+/\s+(\d+)",
                    line,
                )

                if d:

                    # Skip some random ones
                    if randint(0, 10) == 5:
                        continue

                    first_name_1 = d.groups()[1].capitalize()
                    last_name_1 = d.groups()[2].capitalize()
                    first_name_2 = d.groups()[3].capitalize()
                    last_name_2 = d.groups()[4].capitalize()
                    abf_1 = d.groups()[5]
                    abf_2 = d.groups()[6]

                    make_data(abf_1, first_name_1, last_name_1, club, membership)
                    make_data(abf_2, first_name_2, last_name_2, club, membership)
