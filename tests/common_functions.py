"""Common functions used across all tests"""
from selenium.common.exceptions import StaleElementReferenceException

from tests.test_manager import CobaltTestManager


def cobalt_htmx_user_search(
    manager: CobaltTestManager, search_button_id: str, user_system_id: str
):
    """Drive Cobalt HTMX user search to add a user

    Args:
        manager: standard manager object
        search_button_id: id of the button to press to bring up the search
        user_system_id: which user to add
    """

    # User Search button - could be reloaded, so try to fix if stale
    try:
        manager.selenium_wait_for(search_button_id).click()
    except StaleElementReferenceException:
        manager.selenium_wait_for(search_button_id).click()

    # Wait for modal to appear and enter system number in
    system_number = manager.selenium_wait_for_clickable("id_system_number")
    system_number.click()
    system_number.send_keys(user_system_id)

    # click on system number search
    manager.driver.find_element_by_id("id_button_system_number_search").click()

    # Wait for search results and click ok
    manager.selenium_wait_for("id_cobalt_search_ok").click()
