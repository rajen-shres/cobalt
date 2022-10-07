from copy import copy, deepcopy
from decimal import Decimal

from club_sessions.models import Session, SessionType, SessionEntry
from club_sessions.views.core import (
    bridge_credits_for_club,
    iou_for_club,
    edit_session_entry_handle_bridge_credits,
    edit_session_entry_handle_ious,
    edit_session_entry_handle_other,
)
from organisations.models import Organisation
from payments.models import OrgPaymentMethod, MemberTransaction
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
        self.cash = OrgPaymentMethod.objects.filter(
            active=True, organisation=self.club, payment_method="Cash"
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
        self.session_entry.payment_method = self.cash
        self.session_entry.is_paid = False
        self.session_entry.save()

        # Not a registered user
        message, self.session_entry, original_session_entry = _call_helper(
            self, "bridge credits", is_user=False
        )

        self.manager.save_results(
            status=self.session_entry == original_session_entry,
            test_name="Not a registered user",
            test_description="Pass a flag showing user isn't registered, should not do anything",
            output=_output_helper(message, self.session_entry, original_session_entry),
        )

        # Pay cash
        message, self.session_entry, original_session_entry = _call_helper(
            self, "other", new_is_paid=True
        )

        self.manager.save_results(
            status=self.session_entry.is_paid,
            test_name="Pay cash successful",
            test_description="Mark as paid using cash",
            output=_output_helper(message, self.session_entry, original_session_entry),
        )

        # Pay bridge credits
        self.session_entry.is_paid = False
        self.session_entry.payment_method = self.bridge_credits
        message, self.session_entry, original_session_entry = _call_helper(
            self,
            "bridge_credits",
            new_payment_method=self.bridge_credits,
            new_is_paid=True,
            old_is_paid=False,
        )

        alan_last_tran = (
            MemberTransaction.objects.filter(member=self.manager.alan)
            .order_by("pk")
            .last()
        )
        message = f"{message}<br>Alan Trans: {alan_last_tran.description} {alan_last_tran.amount}"

        status = (
            alan_last_tran.amount == -self.session_entry.fee
            and self.session_entry.is_paid
        )

        self.manager.save_results(
            status=status,
            test_name="Pay bridge credits successful",
            test_description="Mark as paid using bridge credits, Alan can afford to pay",
            output=_output_helper(message, self.session_entry, original_session_entry),
        )

        # Cancel bridge credits
        message, self.session_entry, original_session_entry = _call_helper(
            self, "bridge_credits", new_is_paid=False
        )

        alan_last_tran = (
            MemberTransaction.objects.filter(member=self.manager.alan)
            .order_by("pk")
            .last()
        )
        message = f"Message: {message}<br>User Last Tran: {alan_last_tran.description}<br>User last amount: {alan_last_tran.amount}"

        status = (
            alan_last_tran.amount == self.session_entry.fee
            and not self.session_entry.is_paid
        )

        self.manager.save_results(
            status=status,
            test_name="Refund bridge credits successful",
            test_description="Refund bridge credits for Alan",
            output=_output_helper(message, self.session_entry, original_session_entry),
        )


def _call_helper(
    main_class: SessionEntryChangesTests,
    tran_type: str,
    is_user=True,
    old_payment_method=None,
    new_payment_method=None,
    old_fee=None,
    new_fee=None,
    old_is_paid="NotSet",
    new_is_paid="NotSet",
):
    """helper function for calling edit_session_entry_handle_bridge_credits"""

    # Fill in blanks with default values
    if not old_payment_method:
        old_payment_method = main_class.session_entry.payment_method
    if not new_payment_method:
        new_payment_method = main_class.session_entry.payment_method
    if not old_fee:
        old_fee = main_class.session_entry.fee
    if not new_fee:
        new_fee = main_class.session_entry.fee
    if old_is_paid == "NotSet":
        old_is_paid = main_class.session_entry.is_paid
    if new_is_paid == "NotSet":
        new_is_paid = main_class.session_entry.is_paid

    original_session = deepcopy(main_class.session_entry)

    if tran_type == "bridge_credits":

        message, session_entry = edit_session_entry_handle_bridge_credits(
            main_class.club,
            main_class.session,
            main_class.session_entry,
            main_class.manager.alan,
            is_user=is_user,
            old_payment_method=old_payment_method,
            new_payment_method=new_payment_method,
            old_fee=Decimal(old_fee),
            new_fee=Decimal(new_fee),
            old_is_paid=old_is_paid,
            new_is_paid=new_is_paid,
        )

    elif tran_type == "iou":

        message, session_entry = edit_session_entry_handle_ious(
            main_class.club,
            main_class.session_entry,
            main_class.manager.alan,
            is_user=is_user,
            old_payment_method=old_payment_method,
            new_payment_method=new_payment_method,
            old_fee=Decimal(old_fee),
            new_fee=Decimal(new_fee),
            old_is_paid=old_is_paid,
            new_is_paid=new_is_paid,
        )

    else:
        message, session_entry = edit_session_entry_handle_other(
            main_class.club,
            main_class.session_entry,
            main_class.manager.alan,
            is_user=is_user,
            old_payment_method=old_payment_method,
            new_payment_method=new_payment_method,
            old_fee=Decimal(old_fee),
            new_fee=Decimal(new_fee),
            old_is_paid=old_is_paid,
            new_is_paid=new_is_paid,
        )

    return message, session_entry, original_session


def _output_helper(
    message, session_entry: SessionEntry, original_session_entry: SessionEntry
):
    """format the output for the save_results function"""

    ret = f"{message}<br><ul>"

    if session_entry.payment_method != original_session_entry.payment_method:
        ret += f"<li>Payment Method changed to {session_entry.payment_method} from {original_session_entry.payment_method}"
    if session_entry.fee != original_session_entry.fee:
        ret += (
            f"<li>Fee changed to {session_entry.fee} from {original_session_entry.fee}"
        )
    if session_entry.is_paid != original_session_entry.is_paid:
        ret += f"<li>Is_paid changed to {session_entry.is_paid} from {original_session_entry.is_paid}"

    ret += "</ul>"

    if ret == f"{message}<br><ul></ul>":
        ret = f"{message} <br><br>Session entry unchanged by call"

    return ret
