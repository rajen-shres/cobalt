"""Tests for things a member is likely to do that uses payments"""

import time

from django.urls import reverse

from payments.core import get_balance
from payments.models import MemberTransaction
from payments import forms

from payments.tests.common_functions import (
    setup_auto_top_up,
    check_balance_for_user,
    check_last_transaction_for_user,
)
from tests.test_manager import CobaltTestManager


class MemberTransfer:
    """Member transfer related activities"""

    def __init__(self, manager: CobaltTestManager):
        self.manager = manager
        self.client = self.manager.client

    def a1_member_transfer_with_sufficient_funds(self):
        """Transfer to another member with sufficient funds in account"""

        # Set up betty to transfer to
        betty = self.manager.get_user(username="101")
        alan = self.manager.test_user  # shorthand

        # Check Alan's balance before
        alan_expected_initial_balance = 400.0
        check_balance_for_user(
            self.manager,
            alan,
            alan_expected_initial_balance,
            "Check initial balance for Alan",
        )

        return

        # Check Betty's balance before
        betty_expected_initial_balance = 404.44
        check_balance_for_user(
            self.manager,
            betty,
            betty_expected_initial_balance,
            "Check initial balance for Betty",
        )

        # Transfer from Alan to Betty
        desc = "Al to Betty, test transfer"
        amt = 54.45

        # Test the form
        form_data = {
            "transfer_to": betty,
            "amount": amt,
            "description": desc,
        }

        form = forms.MemberTransfer(data=form_data)

        self.manager.results(
            form.is_valid(), "Check member transfer FORM - Alan to Betty", form.errors
        )

        # Test the view - actually do the transfer
        view_data = {
            "transfer_to": betty.id,
            "amount": amt,
            "description": desc,
        }

        url = reverse("payments:member_transfer")
        response = self.client.post(url, view_data)

        self.manager.results(
            response.status_code, "Execute member transfer over view - Alan to Betty"
        )

        # Check after

        # Betty side
        check_last_transaction_for_user(
            self.manager,
            betty,
            desc,
            amt,
            "Execute member transfer over view - Alan to Betty. Betty transaction",
            alan,
        )

        # Alan side
        check_last_transaction_for_user(
            self.manager,
            alan,
            desc,
            -amt,
            "Execute member transfer over view - Alan to Betty. Alan transaction",
            betty,
        )

        # Check Alan's balance after
        check_balance_for_user(
            self.manager,
            alan,
            alan_expected_initial_balance - amt,
            "Execute member transfer over view - Alan to Betty. Alan balance",
        )

        # Check Betty's balance after
        check_balance_for_user(
            self.manager,
            betty,
            betty_expected_initial_balance + amt,
            "Execute member transfer over view - Alan to Betty. Betty balance",
        )

    def a2_member_auto_top_up_enable(self):
        """Enable auto top up"""
        alan = self.manager.test_user
        betty = self.manager.get_user(username="101")

        return

        # set it ip
        setup_auto_top_up(self.manager)
        self.manager.results(
            True,
            "Turn on auto top up for Alan",
            "Hardcoded result. Tests follow.",
        )

        # Check auto top up
        test = bool(alan.stripe_auto_confirmed)
        self.manager.results(
            test,
            "Check auto top up flag turned on for Alan",
            "Expected stripe_auto_confirmed=True",
        )

        # Check auto top up amount
        test = alan.auto_amount == 100
        self.manager.results(
            test,
            "Check auto top up amount for Alan",
            f"Expected $50, got ${alan.auto_amount}",
        )

        # Trigger auto top up
        amt = 500.0
        desc = "Trigger Auto"
        view_data = {
            "transfer_to": betty.id,
            "amount": amt,
            "description": desc,
        }

        url = reverse("payments:member_transfer")
        response = self.client.post(url, view_data)

        self.manager.results(
            response.status_code,
            "Manual transfer to trigger auto top up - Alan to Betty",
        )

        # Give Stripe time to call us back
        time.sleep(5)

        # Check after

        # Betty side
        betty_tran = (
            MemberTransaction.objects.filter(member=betty)
            .order_by("-created_date")
            .first()
        )

        if betty_tran.description == desc and float(betty_tran.amount) == amt:
            test_result = True
        else:
            test_result = False

        result = f"Expected {amt} and '{desc}'. Got {betty_tran.amount} and '{betty_tran.description}'"

        self.manager.results(
            test_result,
            "Execute member transfer over view - Alan to Betty. Betty transaction",
            result,
        )

        alan_balance = get_balance(alan)

        test = alan_balance == 500.0

        self.manager.results(
            test,
            "Manual transfer to trigger auto top up - Alan balance",
            f"Expected $500. Got {alan_balance}",
        )
