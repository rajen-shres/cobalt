"""Common functions used across all tests"""
from selenium.common.exceptions import StaleElementReferenceException

from tests.test_manager import CobaltTestManager


def cobalt_htmx_user_search(
    manager: CobaltTestManager,
    search_button_id: str,
    user_system_id: str,
    search_id: str = None,
):
    """Drive Cobalt HTMX user search to add a user

    Args:
        manager: standard manager object
        search_button_id: id of the button to press to bring up the search
        search_id: search id set for this user search
        user_system_id: which user to add
    """
    print("inside")
    print("waiting for:", search_button_id)
    # User Search button - could be reloaded, so try to fix if stale
    try:
        manager.selenium_wait_for(search_button_id).click()
    except StaleElementReferenceException:
        manager.selenium_wait_for(search_button_id).click()
    print("waiting for:", "id_system_number" + search_id)
    # Wait for modal to appear and enter system number in
    system_number = manager.selenium_wait_for_clickable("id_system_number" + search_id)
    system_number.click()
    print("send keys to:", user_system_id)
    system_number.send_keys(user_system_id)

    # click on system number search
    print("lookung for:", "id_button_system_number_search" + search_id)
    manager.driver.find_element_by_id(
        "id_button_system_number_search" + search_id
    ).click()

    # Wait for search results and click ok
    print("waiting for:", "id_cobalt_search_ok" + search_id)
    manager.selenium_wait_for("id_cobalt_search_ok" + search_id).click()
