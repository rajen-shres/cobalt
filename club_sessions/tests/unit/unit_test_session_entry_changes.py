from decimal import Decimal

from club_sessions.models import Session, SessionType, SessionEntry
from club_sessions.views.core import (
    bridge_credits_for_club,
    iou_for_club,
    edit_session_entry_handle_bridge_credits,
)
from organisations.models import Organisation
from payments.models import OrgPaymentMethod
from tests.test_manager import CobaltTestManagerIntegration


class SessionEntryChangesTests:
    """Unit tests Session Entry changes such as changing payment method, or fee"""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager

        # load static
        self.club = Organisation.objects.filter(name="Payments Bridge Club").first()
        session_type = SessionType.objects.filter(organisation=self.club).first()
        self.bridge_credits = bridge_credits_for_club(self.club)
        self.iou = iou_for_club(self.club)

        # All other payment methods are the same - use bank transfer for no good reason
        self.bank_transfer = OrgPaymentMethod.objects.filter(
            active=True, organisation=self.club, payment_method="Bank Transfer"
        ).first()

        # create a session
        self.session = Session(
            director=self.manager.alan,
            session_type=session_type,
            description="Testing session entries",
        )
        self.session.save()

        # create a session entry
        self.session_entry = SessionEntry(
            session=self.session,
            system_number=100,
            pair_team_number=1,
            seat="N",
            payment_method=self.bridge_credits,
            fee=20,
            is_paid=False,
        )
        self.session_entry.save()

    def bridge_credit_tests(self):
        """Tests for changes to bridge credits"""

        # initial state
        self.session_entry.is_paid = False
        self.session_entry.payment_method = self.bridge_credits
        self.session_entry.is_paid = False
        self.session_entry.save()

        message, session_entry = edit_session_entry_handle_bridge_credits(
            self.club,
            self.session_entry,
            self.manager.alan,
            is_user=False,
            old_payment_method=self.bridge_credits,
            new_payment_method=self.bridge_credits,
            old_fee=Decimal(5),
            new_fee=Decimal(5),
            old_is_paid=True,
            new_is_paid=True,
        )

        self.manager.save_results(
            status=True,
            test_name="Added session",
            test_description="Added session",
            output=f"message - {message}",
        )
