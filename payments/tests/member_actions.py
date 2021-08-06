"""Tests for things a member is likely to do that uses payments"""

import time
from pprint import pprint

from django.test import Client
from django.urls import reverse

from accounts.models import User
from payments.core import get_balance
from payments.models import MemberTransaction
from payments import forms


class MemberTransfer:
    """Member transfer related activities"""

    def __init__(self, manager):
        self.manager = manager
        self.client = self.manager.client
        self.py = self.manager.py

    def a1_member_transfer_with_sufficient_funds(self):
        """Transfer to another member with sufficient funds in account"""

        # Check Alan's balance before
        alan_expected_initial_balance = 400.0
        alan_balance = get_balance(self.manager.test_user)
        test = alan_balance == alan_expected_initial_balance
        self.manager.results(
            test,
            "Check initial balance for Alan",
            f"Expected ${alan_expected_initial_balance}, got ${alan_balance}",
        )

        # Check Betty's balance before
        betty = self.manager.get_user(username="101")
        betty_expected_initial_balance = 404.44
        betty_balance = get_balance(betty)
        test = betty_balance == betty_expected_initial_balance
        self.manager.results(
            test,
            "Check initial balance for Betty",
            f"Expected ${betty_expected_initial_balance}, got ${betty_balance}",
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

        # Alan side
        alan_tran = (
            MemberTransaction.objects.filter(member=self.manager.test_user)
            .order_by("-created_date")
            .first()
        )

        if alan_tran.description == desc and float(alan_tran.amount) == -amt:
            test = True
        else:
            test = False

        result = f"Expected {-amt} and '{desc}'. Got {alan_tran.amount} and '{alan_tran.description}'"

        self.manager.results(
            test,
            "Execute member transfer over view - Alan to Betty. Alan transaction",
            result,
        )

        # Check Alan's balance
        alan_new_balance = float(get_balance(self.manager.test_user))
        alan_expected_new_balance = float(alan_expected_initial_balance) - amt
        test = alan_new_balance == alan_expected_new_balance
        self.manager.results(
            test,
            "Check final balance for Alan",
            f"Expected ${alan_expected_new_balance}, got ${alan_new_balance}",
        )

        # Check Betty's balance
        betty_new_balance = float(get_balance(betty))
        betty_expected_new_balance = float(betty_expected_initial_balance) + amt
        test = betty_new_balance == betty_expected_new_balance
        self.manager.results(
            test,
            "Check final balance for Betty",
            f"Expected ${betty_expected_new_balance}, got ${betty_new_balance}",
        )
