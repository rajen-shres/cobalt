from copy import copy, deepcopy
from decimal import Decimal
from typing import Union

from club_sessions.models import Session, SessionType, SessionEntry
from club_sessions.views.core import (
    bridge_credits_for_club,
    iou_for_club,
    edit_session_entry_handle_bridge_credits,
    edit_session_entry_handle_ious,
    edit_session_entry_handle_other,
)
from organisations.models import Organisation
from payments.models import OrgPaymentMethod, MemberTransaction, UserPendingPayment
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
        self.session_entry.save()

        #############################
        # Not a registered user
        #############################
        message, self.session_entry, original_session_entry = _call_helper(
            self, "bridge_credits", is_user=False
        )

        self.manager.save_results(
            status=self.session_entry == original_session_entry,
            test_name="Not a registered user rejected",
            test_description="Pass a flag showing user isn't registered, should not do anything",
            output=_output_helper(message, self.session_entry, original_session_entry),
        )

        #############################
        # Pay bridge credits
        #############################
        message, self.session_entry, original_session_entry = _call_helper(
            self,
            "bridge_credits",
            new_payment_method=self.bridge_credits,
            new_is_paid=True,
            old_is_paid=False,
        )

        message, alan_last_tran = _last_tran_helper(message, self.manager.alan)

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

        #############################
        # Cancel bridge credits
        #############################
        message, self.session_entry, original_session_entry = _call_helper(
            self, "bridge_credits", new_is_paid=False
        )

        message, alan_last_tran = _last_tran_helper(message, self.manager.alan)

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

        #############################
        # bridge credits with fee change
        #############################
        message, self.session_entry, original_session_entry = _call_helper(
            self, "bridge_credits", new_is_paid=True, new_fee=50
        )

        message, alan_last_tran = _last_tran_helper(message, self.manager.alan)

        status = (
            alan_last_tran.amount == -self.session_entry.fee
            and alan_last_tran.amount == -Decimal(50)
            and self.session_entry.is_paid
        )

        self.manager.save_results(
            status=status,
            test_name="Bridge credits with fee change successful",
            test_description="Pay bridge credits for Alan and change the fee at the same time",
            output=_output_helper(message, self.session_entry, original_session_entry),
        )
        #############################
        # bridge credits with fee change and change of entry type
        #############################
        self.session_entry.is_paid = False
        self.session_entry.payment_method = self.cash
        self.session_entry.fee = Decimal(2)
        self.session_entry.save()

        message, self.session_entry, original_session_entry = _call_helper(
            self,
            "bridge_credits",
            new_is_paid=True,
            new_fee=50,
            new_payment_method=self.bridge_credits,
        )

        message, alan_last_tran = _last_tran_helper(message, self.manager.alan)

        status = (
            alan_last_tran.amount == -self.session_entry.fee
            and alan_last_tran.amount == -Decimal(50)
            and self.session_entry.is_paid
        )

        self.manager.save_results(
            status=status,
            test_name="Bridge credits with fee change and type change successful",
            test_description="Pay bridge credits for Alan and change the fee and payment method at the same time",
            output=_output_helper(message, self.session_entry, original_session_entry),
        )
        #############################
        # bridge credits with change fee on paid entry
        #############################
        self.session_entry.is_paid = True
        self.session_entry.payment_method = self.bridge_credits
        self.session_entry.fee = Decimal(5)
        self.session_entry.save()

        message, self.session_entry, original_session_entry = _call_helper(
            self, "bridge_credits", new_fee=25
        )

        message, alan_last_tran = _last_tran_helper(message, self.manager.alan)

        status = self.session_entry == original_session_entry

        self.manager.save_results(
            status=status,
            test_name="Bridge credits change fee on paid entry blocked",
            test_description="Try to change the fee on a paid bridge credit entry. Should fail.",
            output=_output_helper(message, self.session_entry, original_session_entry),
        )

    def cash_tests(self):
        """Tests for changes to bridge credits"""

        # initial state
        self.session_entry.is_paid = False
        self.session_entry.payment_method = self.cash
        self.session_entry.save()

        #############################
        # Pay cash
        #############################
        message, self.session_entry, original_session_entry = _call_helper(
            self, "other", new_is_paid=True
        )

        self.manager.save_results(
            status=self.session_entry.is_paid,
            test_name="Pay cash successful",
            test_description="Mark as paid using cash",
            output=_output_helper(message, self.session_entry, original_session_entry),
        )
        #############################
        # un-Pay cash
        #############################
        message, self.session_entry, original_session_entry = _call_helper(
            self, "other", new_is_paid=False
        )

        self.manager.save_results(
            status=not self.session_entry.is_paid,
            test_name="Un-Pay cash successful",
            test_description="Mark as unpaid using cash",
            output=_output_helper(message, self.session_entry, original_session_entry),
        )

    def iou_tests(self):
        """Tests for changes to ious"""

        # initial state
        self.session_entry.is_paid = False
        self.session_entry.payment_method = self.iou
        self.session_entry.fee = Decimal(19)
        self.session_entry.save()

        #############################
        # Pay iou
        #############################
        message, self.session_entry, original_session_entry = _call_helper(
            self,
            "iou",
            new_is_paid=True,
            old_is_paid=False,
        )

        message, alan_last_iou = _iou_helper(message, self.manager.alan)

        status = (
            alan_last_iou.amount == self.session_entry.fee
            and self.session_entry.is_paid
        )

        self.manager.save_results(
            status=status,
            test_name="Pay iou successful",
            test_description="Mark as paid using iou and generate an IOU",
            output=_output_helper(message, self.session_entry, original_session_entry),
        )

        #############################
        # Un-Pay iou
        #############################
        message, self.session_entry, original_session_entry = _call_helper(
            self,
            "iou",
            new_is_paid=False,
            old_is_paid=True,
        )

        message, alan_last_iou = _iou_helper(message, self.manager.alan)

        status = not alan_last_iou and not self.session_entry.is_paid

        self.manager.save_results(
            status=status,
            test_name="Un-pay iou successful",
            test_description="Mark as unpaid using iou and cancel an IOU",
            output=_output_helper(message, self.session_entry, original_session_entry),
        )

        #############################
        # Pay iou and change fee
        #############################
        self.session_entry.fee = Decimal(2)
        message, self.session_entry, original_session_entry = _call_helper(
            self,
            "iou",
            new_is_paid=True,
            old_is_paid=False,
            old_fee=Decimal(2),
            new_fee=Decimal(11),
        )

        message, alan_last_iou = _iou_helper(message, self.manager.alan)

        status = (
            alan_last_iou.amount == self.session_entry.fee
            and self.session_entry.is_paid
            and self.session_entry.fee == Decimal(11)
        )

        self.manager.save_results(
            status=status,
            test_name="Pay iou and change fee successful",
            test_description="Mark as paid using iou and change fee and generate an IOU",
            output=_output_helper(message, self.session_entry, original_session_entry),
        )
        #############################
        # Pay iou and change payment type
        #############################
        self.session_entry.fee = Decimal(2)
        self.session_entry.is_paid = False
        self.session_entry.payment_method = self.cash
        self.session_entry.save()

        message, self.session_entry, original_session_entry = _call_helper(
            self,
            "iou",
            new_is_paid=True,
            old_is_paid=False,
            old_fee=Decimal(2),
            new_fee=Decimal(2),
            old_payment_method=self.cash,
            new_payment_method=self.iou,
        )

        message, alan_last_iou = _iou_helper(message, self.manager.alan)

        status = (
            alan_last_iou.amount == self.session_entry.fee
            and self.session_entry.is_paid
            and self.session_entry.fee == Decimal(2)
        )

        self.manager.save_results(
            status=status,
            test_name="Pay iou and change payment type successful",
            test_description="Mark as paid using iou and change payment type and generate an IOU",
            output=_output_helper(message, self.session_entry, original_session_entry),
        )

        #############################
        # Pay iou and change fee and payment type
        #############################
        self.session_entry.fee = Decimal(2)
        self.session_entry.is_paid = False
        self.session_entry.payment_method = self.cash
        self.session_entry.save()

        message, self.session_entry, original_session_entry = _call_helper(
            self,
            "iou",
            new_is_paid=True,
            old_is_paid=False,
            old_fee=Decimal(2),
            new_fee=Decimal(13),
            old_payment_method=self.cash,
            new_payment_method=self.iou,
        )

        message, alan_last_iou = _iou_helper(message, self.manager.alan)

        status = (
            alan_last_iou.amount == self.session_entry.fee
            and self.session_entry.is_paid
            and self.session_entry.fee == Decimal(13)
        )

        self.manager.save_results(
            status=status,
            test_name="Pay iou and change fee and change payment type successful",
            test_description="Mark as paid using iou and change fee and change payment type and generate an IOU",
            output=_output_helper(message, self.session_entry, original_session_entry),
        )

        #############################
        # Change fee on paid IOU
        #############################
        self.session_entry.fee = Decimal(2)
        self.session_entry.is_paid = True
        self.session_entry.payment_method = self.iou
        self.session_entry.save()

        message, self.session_entry, original_session_entry = _call_helper(
            self,
            "iou",
            old_fee=Decimal(2),
            new_fee=Decimal(17),
        )

        message, alan_last_iou = _iou_helper(message, self.manager.alan)

        status = self.session_entry == original_session_entry

        self.manager.save_results(
            status=status,
            test_name="Change fee on a paid iou blocked",
            test_description="Try to change a fee on a paid IOU. Should be rejected.",
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
    old_is_paid: Union[bool, str] = "NotSet",
    new_is_paid: Union[bool, str] = "NotSet",
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

    table = "<br><table class='table table-primary'><tr><th>Parameter<th>Before<th>After</tr>"
    ret = f"{message}{table}"

    if session_entry.payment_method != original_session_entry.payment_method:
        ret += f"<tr><td>Payment Method<td>{original_session_entry.payment_method.payment_method}<td>{session_entry.payment_method.payment_method}</tr>"
    if session_entry.fee != original_session_entry.fee:
        ret += (
            f"<tr><td>Fee<td>{original_session_entry.fee}<td>{session_entry.fee}</tr>"
        )
    if session_entry.is_paid != original_session_entry.is_paid:
        ret += f"<tr><td>Is_paid<td>{original_session_entry.is_paid}<td>{session_entry.is_paid}</tr>"

    ret += "</table>"

    if ret == f"{message}{table}":
        ret = f"{message} <br><br>Session entry unchanged by call"

    return ret


def _simple_table(dictionary):
    ret = "<table class='table table-dark'>"

    for key in dictionary:
        ret += f"<tr><td class='align-top'>{key}<td>{dictionary[key]}</tr>"

    ret += "</table>"

    return ret


def _last_tran_helper(message, alan):
    """used for transactions where a payment is made. Shows Alan's last transaction"""

    alan_last_tran = MemberTransaction.objects.filter(member=alan).order_by("pk").last()

    dictionary = {
        "Message": message,
        "User Last Tran": alan_last_tran.description,
        "User last amount": alan_last_tran.amount,
    }

    return _simple_table(dictionary), alan_last_tran


def _iou_helper(message, alan):
    """used for ious where a payment is made. Shows Alan's ious"""

    alan_last_iou = (
        UserPendingPayment.objects.filter(system_number=alan.system_number)
        .order_by("pk")
        .last()
    )

    if alan_last_iou:

        dictionary = {
            "Message": message,
            "User IOU": alan_last_iou.description,
            "User IOU amount": alan_last_iou.amount,
        }
    else:

        dictionary = {
            "Message": message,
            "User IOU": "No IOU found",
        }

    return _simple_table(dictionary), alan_last_iou
