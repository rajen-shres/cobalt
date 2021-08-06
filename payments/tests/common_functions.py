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


def setup_auto_top_up(manager, user=None):
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


def check_last_transaction_for_user(manager, user, desc, amt, msg):
    """Check if last transaction is as expected"""
    stack = inspect.stack()
    calling_class = stack[1][0].f_locals["self"].__class__.__name__
    calling_method = stack[1][0].f_code.co_name

    user_tran = (
        MemberTransaction.objects.filter(member=user).order_by("-created_date").first()
    )

    if user_tran.description == desc and float(user_tran.amount) == amt:
        test_result = True
    else:
        test_result = False

    result = f"Expected {amt} and '{desc}'. Got {user_tran.amount} and '{user_tran.description}'"

    manager.results(test_result, msg, result, calling_class, calling_method)


def check_balance_for_user(manager, user, expected_balance, msg):
    """Check and return balance"""
    stack = inspect.stack()
    calling_class = stack[1][0].f_locals["self"].__class__.__name__
    calling_method = stack[1][0].f_code.co_name

    user_balance = get_balance(user)
    test = user_balance == expected_balance
    manager.results(
        test,
        msg,
        f"Expected ${expected_balance}, got ${user_balance}",
        calling_class,
        calling_method,
    )

    return user_balance
