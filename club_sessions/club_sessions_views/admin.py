from decimal import Decimal

from club_sessions.models import (
    SessionType,
    MasterSessionType,
    SessionTypePaymentMethod,
    SessionTypePaymentMethodMembership,
    DEFAULT_FEE,
)
from organisations.models import MembershipType
from payments.models import OrgPaymentMethod

DEFAULT_PAYMENT_METHODS = ["Cash", "EFTPOS", "Credit Card", "Bank Transfer"]
DEFAULT_SESSION_TYPES = [
    MasterSessionType.DUPLICATE,
    #    MasterSessionType.MULTI_SESSION,
    #    MasterSessionType.WORKSHOP,
]


def add_payment_method_session_type_combos(club):
    """Add the required instances of SessionTypePaymentMethod and SessionTypePaymentMethodMembership if
    they do not already exist"""

    print("club is", club)

    sess_types = SessionType.objects.filter(organisation=club)
    pay_meths = OrgPaymentMethod.objects.filter(organisation=club).filter(active=True)

    for pay_meth_item in pay_meths:
        for sess_type_item in sess_types:
            sess_type_pay_method, _ = SessionTypePaymentMethod.objects.get_or_create(
                session_type=sess_type_item, payment_method=pay_meth_item
            )

            # Now create the SessionTypePaymentMethodMembership items.
            # Add non-member fee first so it will line up properly on the edit table
            spmm, created = SessionTypePaymentMethodMembership.objects.get_or_create(
                session_type_payment_method=sess_type_pay_method,
                membership=None,
            )
            if created:
                spmm.fee = DEFAULT_FEE
                spmm.save()

            membership_types = MembershipType.objects.filter(organisation=club)
            for membership_type in membership_types:
                (
                    spmm,
                    created,
                ) = SessionTypePaymentMethodMembership.objects.get_or_create(
                    session_type_payment_method=sess_type_pay_method,
                    membership=membership_type,
                )
                if created:
                    spmm.fee = DEFAULT_FEE
                    spmm.save()


def add_club_session_defaults(club):
    """When we add a club we set up some sensible defaults"""

    # Payment Methods
    for default_payment_method in DEFAULT_PAYMENT_METHODS:

        OrgPaymentMethod(
            organisation=club, payment_method=default_payment_method, active=True
        ).save()

    # Session Type
    for default_session_type in DEFAULT_SESSION_TYPES:

        SessionType(
            name=default_session_type.label,
            organisation=club,
            master_session_type=default_session_type.value,
        ).save()

    add_payment_method_session_type_combos(club)


def add_club_session(
    club, session_name, master_session_type=MasterSessionType.DUPLICATE.value
):
    """Add a new session to a club"""

    SessionType(
        name=session_name,
        organisation=club,
        master_session_type=master_session_type,
    ).save()

    add_payment_method_session_type_combos(club)


def turn_off_payment_type(club):
    """Handle a payment type being disabled for a club. We need to remove this payment from the session tables"""

    print(
        SessionTypePaymentMethod.objects.filter(
            payment_method__organisation=club
        ).filter(payment_method__active=False)
    )
    SessionTypePaymentMethod.objects.filter(payment_method__organisation=club).filter(
        payment_method__active=False
    ).delete()
