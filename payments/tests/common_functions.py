import inspect
import time
from pprint import pprint

from django.test import Client
from django.urls import reverse

from accounts.models import User
from payments.core import get_balance
from payments.models import MemberTransaction
from payments import forms

from selenium.webdriver.common.by import By

from tests.test_manager import CobaltTestManager

"""
    Common functions for payments.
"""


def setup_auto_top_up(manager: CobaltTestManager, user: User = None):
    """Selenium function to set up auto top up

    Args:
        manager: test_manager.Manager object for interacting with system
        user: User object representing user to set up (optional)
    """

    # login this user
    if user:
        manager.login_selenium_user(user)

    # Go to auto top up screen
    manager.driver.get(f"{manager.base_url}/payments/setup-autotopup")

    # wait for iFrame to load the old fashioned way
    time.sleep(3)

    # Stripe fields are in an iFrame, we need to switch to that to find them
    manager.driver.switch_to.frame(manager.driver.find_element_by_tag_name("iframe"))

    # Enter details
    manager.driver.find_element_by_css_selector('input[name="cardnumber"]').send_keys(
        "4242424242424242"
    )
    manager.driver.find_element_by_css_selector('input[name="exp-date"]').send_keys(
        "0235"
    )
    manager.driver.find_element_by_css_selector('input[name="cvc"]').send_keys("999")

    # Switch back to main part of document
    manager.driver.switch_to.default_content()

    # Hit submit
    manager.driver.find_element(By.ID, "submit").click()

    # Login main user again
    if user:
        manager.login_selenium_user(manager.test_user)


def check_last_transaction_for_user(
    manager: CobaltTestManager,
    user: User,
    tran_desc,
    tran_amt,
    test_name,
    other_member=None,
    test_description=None,
):
    """Check if last transaction is as expected"""

    user_tran = (
        MemberTransaction.objects.filter(member=user).order_by("-created_date").first()
    )

    if other_member:
        if (
            user_tran.description == tran_desc
            and float(user_tran.amount) == tran_amt
            and other_member == user_tran.other_member
        ):
            test_result = True
        else:
            test_result = False
        result = f"Expected {other_member}, {tran_amt} and '{tran_desc}'. Got {user_tran.other_member}, {user_tran.amount} and '{user_tran.description}'"
    else:
        if user_tran.description == tran_desc and float(user_tran.amount) == tran_amt:
            test_result = True
        else:
            test_result = False

        result = f"Expected {tran_amt} and '{tran_desc}'. Got {user_tran.amount} and '{user_tran.description}'"

    manager.save_results(
        status=test_result,
        test_name=test_name,
        output=result,
        test_description=test_description,
    )


def check_balance_for_user(
    manager: CobaltTestManager,
    user: User = None,
    expected_balance=0,
    test_name=None,
    test_description=None,
):
    """Check and return balance"""

    user_balance = get_balance(user)
    test_result = user_balance == expected_balance

    manager.save_results(
        status=test_result,
        test_name=test_name,
        output=f"Expected ${expected_balance}, got ${user_balance}",
        test_description=test_description,
    )

    return user_balance
