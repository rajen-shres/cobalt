from club_sessions.models import (
    SessionType,
    MasterSessionType,
    SessionTypePaymentMethod,
)
from payments.models import OrgPaymentMethod


def add_club_session_defaults(club):
    """When we add a club we set up some sensible defaults"""

    # Session Type
    session_type = SessionType(
        name="Duplicate",
        organisation=club,
        master_session_type=MasterSessionType.DUPLICATE,
    )
    session_type.save()

    # Payment Methods
    cash = OrgPaymentMethod(organisation=club, payment_method="Cash")
    cash.save()

    # Combination
    SessionTypePaymentMethod(session_type=session_type, payment_method=cash).save()
