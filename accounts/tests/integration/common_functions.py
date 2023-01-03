"""
    Common functions for accounts.
"""
import time

from django.urls import reverse
from selenium.webdriver.common.by import By

from accounts.models import User
from tests.test_manager import CobaltTestManagerIntegration


def register_user(
    manager: CobaltTestManagerIntegration,
    system_number: str,
):
    """Common function to register a user

        Initial Selenium State: Any
        Final Selenium State: On logged in to dashboard

    Args:
        manager: test_manager.Manager object for interacting with system
        system_number: ABF Number
    """

    # go to page
    url = manager.base_url + reverse("accounts:register")
    manager.driver.get(url)

    # Enter ABF Number
    manager.driver.find_element(By.ID, "id_username").send_keys(system_number)

    # Move to email field to fill in name using background search
    manager.driver.find_element(By.ID, "id_email").click()
    time.sleep(1)

    # Enter email
    manager.driver.find_element(By.ID, "id_email").send_keys("a@b.com")

    # Enter password
    manager.driver.find_element(By.ID, "id_password1").send_keys(manager.test_code)
    manager.driver.find_element(By.ID, "id_password2").send_keys(manager.test_code)

    # Enter
    manager.driver.find_element(By.CLASS_NAME, "btn").click()

    # We won't get an email so just mark member as active
    user = User.objects.filter(system_number=system_number).first()
    user.is_active = True
    user.save()

    # login
    manager.login_selenium_user(user)

    manager.save_results(
        status=True,
        test_name=f"Registered user {user.full_name}",
        output=f"Registered user {user}",
        test_description="Registers a new user and checks we can login",
    )
