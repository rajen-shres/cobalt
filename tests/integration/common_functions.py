"""Common functions used across all tests"""
import time

from selenium.common.exceptions import StaleElementReferenceException

from tests.test_manager import CobaltTestManagerIntegration


def cobalt_htmx_user_search(
    manager: CobaltTestManagerIntegration,
    search_button_id: str,
    user_system_id: str,
    search_id="",
):
    """Drive Cobalt HTMX user search to add a user

    Args:
        manager: standard manager object
        search_button_id: id of the button to press to bring up the search
        search_id: search id set for this user search
        user_system_id: which user to add
    """

    print("Waiting for", search_button_id)
    manager.sleep()

    # User Search button
    manager.selenium_wait_for_clickable(search_button_id).click()

    # Wait for modal to appear and enter system number in
    system_number = manager.selenium_wait_for_clickable("id_system_number" + search_id)
    system_number.click()
    system_number.send_keys(user_system_id)

    # click on system number search
    manager.driver.find_element_by_id(
        f"id_button_system_number_search{search_id}"
    ).click()

    # Wait for search results and click ok
    manager.selenium_wait_for_clickable(f"id_cobalt_search_ok{search_id}").click()
