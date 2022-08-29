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

    # set rates to be different (default is the same)
    session_type = SessionType.objects.filter(
        name="Duplicate", organisation=club
    ).first()
    payment_method = OrgPaymentMethod.objects.filter(
        payment_method="Bridge Credits", organisation=club
    ).first()
    session_type_payment_method = SessionTypePaymentMethod.objects.filter(
        session_type=session_type, payment_method=payment_method
    ).first()
    membership = MembershipType.objects.filter(
        organisation=club, name="Standard"
    ).first()
    session = SessionTypePaymentMethodMembership.objects.filter(
        session_type_payment_method=session_type_payment_method, membership=membership
    ).first()
    session.fee = 10
    session.save()

    # Add members
    for system_number in range(100, 120):
        MemberMembershipType(
            system_number=system_number,
            membership_type=membership,
            last_modified_by=alan,
        ).save()


class Command(BaseCommand):
    def handle(self, *args, **options):
        _manage_club("Payments Bridge Club", "8889")
