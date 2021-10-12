from decimal import Decimal

from club_sessions.models import (
    SessionType,
    MasterSessionType,
    SessionTypePaymentMethod,
    SessionTypePaymentMethodMembership,
)
from organisations.models import MembershipType
from payments.models import OrgPaymentMethod

DEFAULT_PAYMENT_METHODS = ["Cash", "EFTPOS", "Credit Card", "Bank Transfer"]
DEFAULT_SESSION_TYPES = [
    MasterSessionType.DUPLICATE,
    MasterSessionType.MULTI_SESSION,
    MasterSessionType.WORKSHOP,
]
DEFAULT_FEE = Decimal(5.0)


def add_club_session_defaults(club):
    """When we add a club we set up some sensible defaults"""

    # Payment Methods
    pay_meth = []

    for default_payment_method in DEFAULT_PAYMENT_METHODS:

        payment_method = OrgPaymentMethod(
            organisation=club, payment_method=default_payment_method, active=False
        )
        payment_method.save()

        pay_meth.append(payment_method)

    # Session Type
    sess_type = []

    for default_session_type in DEFAULT_SESSION_TYPES:

        session_type = SessionType(
            name=default_session_type.label,
            organisation=club,
            master_session_type=default_session_type.value,
        )
        session_type.save()

        sess_type.append(session_type)

    # Combination of the two
    for pay_meth_item in pay_meth:
        for sess_type_item in sess_type:
            sess_type_pay_method = SessionTypePaymentMethod(
                session_type=sess_type_item, payment_method=pay_meth_item
            )
            sess_type_pay_method.save()

            # Now create the SessionTypePaymentMethodMembership items.
            membership_types = MembershipType.objects.filter(organisation=club)
            for membership_type in membership_types:
                SessionTypePaymentMethodMembership(
                    session_type_payment_method=sess_type_pay_method,
                    membership=membership_type,
                    fee=DEFAULT_FEE,
                ).save()

            # Add non-member fee
            SessionTypePaymentMethodMembership(
                session_type_payment_method=sess_type_pay_method,
                membership=None,
                fee=DEFAULT_FEE,
            ).save()
