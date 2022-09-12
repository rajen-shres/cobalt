""" Script to add test data for testing club admin and pre-paid """

from django.core.management.base import BaseCommand

from accounts.models import User
from club_sessions.models import (
    SessionTypePaymentMethodMembership,
    SessionTypePaymentMethod,
    SessionType,
)
from organisations.models import Organisation, MembershipType, MemberMembershipType
from organisations.views.admin import add_club_defaults
from payments.models import OrgPaymentMethod
from rbac.core import (
    rbac_get_group_by_name,
    rbac_add_user_to_group,
    rbac_get_admin_group_by_name,
    rbac_add_user_to_admin_group,
)


def _set_session_rates(club, payment_method_name, membership, amount):
    """Set specific session rats"""

    # set rates to be different (default is the same)
    session_type = SessionType.objects.filter(
        name="Duplicate", organisation=club
    ).first()
    payment_method = OrgPaymentMethod.objects.filter(
        payment_method=payment_method_name, organisation=club
    ).first()
    session_type_payment_method = SessionTypePaymentMethod.objects.filter(
        session_type=session_type, payment_method=payment_method
    ).first()
    session = SessionTypePaymentMethodMembership.objects.filter(
        session_type_payment_method=session_type_payment_method, membership=membership
    ).first()
    session.fee = amount
    session.save()


def _manage_club(name: str, org_id: str):
    # Add a club and set up data

    alan = User.objects.filter(system_number=100).first()
    club = Organisation(
        org_id=org_id,
        name=name,
        secretary=alan,
        type="Club",
        club_email="a@b.com",
        address1="Add1",
        address2="Add2",
        suburb="Suburb",
        state="ACT",
        postcode="1234",
    )
    club.save()

    # Set up defaults as if we were created from the UI
    add_club_defaults(club)

    # Add some session rates
    membership = MembershipType.objects.filter(
        organisation=club, name="Standard"
    ).first()

    _set_session_rates(club, "Bridge Credits", membership, 10)
    _set_session_rates(club, "Cash", membership, 13)
    _set_session_rates(club, "EFTPOS", membership, 14)
    _set_session_rates(club, "Credit Card", membership, 15)

    # Guests
    _set_session_rates(club, "Bridge Credits", None, 20)
    _set_session_rates(club, "Cash", None, 23)
    _set_session_rates(club, "EFTPOS", None, 24)
    _set_session_rates(club, "Credit Card", None, 25)

    # Add members
    for system_number in range(100, 120):
        MemberMembershipType(
            system_number=system_number,
            membership_type=membership,
            last_modified_by=alan,
        ).save()

    # Add me as an admin
    # Get group
    group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.basic")

    for system_number in [620246, 518891]:

        user = User.objects.filter(system_number=system_number).first()

        # Add user to group
        rbac_add_user_to_group(user, group)

        # All users are admins
        admin_group = rbac_get_admin_group_by_name(
            f"{club.rbac_admin_name_qualifier}.admin"
        )
        rbac_add_user_to_admin_group(user, admin_group)


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Adding Payments Bridge Club and data...")
        _manage_club("Payments Bridge Club", "8889")
