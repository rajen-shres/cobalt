"""
    Common functions for organisations.
"""
import time
from pprint import pprint

from django.urls import reverse

from accounts.models import User
from organisations.models import Organisation
from organisations.views.admin import rbac_get_basic_and_advanced
from tests.test_manager import CobaltTestManager


def add_club(
    manager: CobaltTestManager, user: User = None, view_data=None, reverse_result=False
):
    """Common function to try to add a club

    Args:
        manager: test_manager.Manager object for interacting with system
        user: User object
        view_data: dic thing for the view
        reverse_result: swap True for False - we want this to fail
    """

    url = reverse("organisations:admin_add_club")

    # log user in
    manager.login_test_client(user)

    response = manager.client.post(url, view_data)

    ok = response.status_code == 302

    if reverse_result:
        ok = not ok
        desc = f"{user.first_name} adds {view_data['name']} as a club but doesn't have permission.  This should fail. We should get a redirect if it works."
        test_name = (
            f"{user.first_name} adds {view_data['name']}. Should fail - Redirect"
        )
        output = f"Checking we didn't redirected. {ok}"
    else:
        desc = f"{user.first_name} adds {view_data['name']} as a club.  We have to use real club names as this connects to the MPC. We should get a redirect if it works."
        test_name = f"{user.first_name} adds {view_data['name']} - Redirect"
        output = f"Checking we got redirected. {ok}"

    manager.save_results(
        status=ok, test_name=test_name, output=output, test_description=desc
    )

    ok = Organisation.objects.filter(org_id=view_data["org_id"]).exists()

    if reverse_result:
        ok = not ok
        test_name = f"{user.first_name} adds {view_data['name']}. Should fail - Check doesn't exist"
        desc = "Check that an org with this id doesn't exists. This test is expected to fail. Invalid permissions."
        output = f"Shouldn't find org with org_id={view_data['org_id']}. {ok}."
    else:
        test_name = f"{user.first_name} adds {view_data['name']} - Check exists"
        desc = "Check that an org with this id exists. Invalid test if it existed before we tried to add it."
        output = f"Should find org with org_id={view_data['org_id']}. {ok}."

    manager.save_results(
        status=ok,
        test_name=test_name,
        output=output,
        test_description=desc,
    )


def confirm_club_rbac_status(
    manager: CobaltTestManager,
    club_org_id: int,
    expected_status: str,
    test_name: str,
    test_description: str,
    reverse_result=False,
):
    """Common function to test the rbac status of a club

    Args:
        manager: test_manager.Manager object for interacting with system
        club_org_id: org id of club
        expected_status: what the status should be
        test_description: long description of test
        test_name: name of test
        reverse_result: if failure is a good outcome
    """

    club = Organisation.objects.filter(org_id=club_org_id).first()

    basic, advanced = rbac_get_basic_and_advanced(club)

    if basic and advanced:
        rbac_state = "Both basic and advanced"
    elif basic:
        rbac_state = "Basic"
    elif advanced:
        rbac_state = "Advanced"
    else:
        rbac_state = "Not Set Up"

    ok = expected_status == rbac_state

    if reverse_result:
        ok = not ok

    manager.save_results(
        status=ok,
        test_name=test_name,
        output=f"{club} checked for RBAC state to be: '{expected_status}'. Actual state is: '{rbac_state}'",
        test_description=test_description,
    )


def set_rbac_status_as_user(
    manager: CobaltTestManager,
    user: User,
    club_org_id: int,
    new_status: str,
    test_name: str,
    test_description: str,
    reverse_result: bool,
):
    """Common function to change the rbac state of a club and check the outcome. Sometimes we expect this to fail.

    Args:
        manager: test_manager.Manager object for interacting with system
        user: User object
        club_org_id: org id of club
        new_status: status to change to
        test_description: long description of test
        test_name: name of test
        reverse_result: for tests that should fail
    """

    # log user in
    manager.login_test_client(user)

    # Get club
    club = Organisation.objects.filter(org_id=club_org_id).first()

    if new_status == "Advanced":
        url_string = "organisations:admin_club_rbac_convert_basic_to_advanced"

    elif new_status == "Basic":
        url_string = "organisations:admin_club_rbac_convert_advanced_to_basic"

    url = reverse(url_string, kwargs={"club_id": club.id})

    # run - don't bother checking what comes back
    manager.client.post(url)

    # see what the status is now
    confirm_club_rbac_status(
        manager, club_org_id, new_status, test_name, test_description, reverse_result
    )


def change_rbac_status_as_user(
    manager: CobaltTestManager,
    user: User,
    club_org_id: int,
    new_status: str,
    test_name: str,
    test_description: str,
    reverse_result: bool,
):
    """Common function to change the rbac state of a club and check the outcome. Sometimes we expect this to fail.

    Args:
        manager: test_manager.Manager object for interacting with system
        user: User object
        club_org_id: org id of club
        new_status: status to change to
        test_description: long description of test
        test_name: name of test
        reverse_result: for tests that should fail
    """

    # log user in
    manager.login_test_client(user)

    # Get club
    club = Organisation.objects.filter(org_id=club_org_id).first()

    if new_status == "Basic":
        url_string = "organisations:admin_club_rbac_convert_advanced_to_basic"

    elif new_status == "Advanced":
        url_string = "organisations:admin_club_rbac_convert_basic_to_advanced"

    url = reverse(url_string, kwargs={"club_id": club.id})

    # run - don't bother checking what comes back
    manager.client.post(url)

    # see what the status is now
    confirm_club_rbac_status(
        manager, club_org_id, new_status, test_name, test_description, reverse_result
    )


def access_club_menu(
    manager: CobaltTestManager,
    user: User,
    club_id: int,
    expected_club_name: str,
    test_name: str,
    test_description: str,
    reverse_result=False,
):
    """Common function to check access to the club menu for different users

        The club menu uses a lot of HTMX so we access this through Selenium.

        Initial Selenium State: Any
        Final Selenium State: On front page of Club Menu for provided club name as provided user

    Args:
        manager: test_manager.Manager object for interacting with system
        user: User object
        club_id: Django id of club, not org_id
        expected_club_name: name we expect to find in the H1
        test_description: long description of test
        test_name: name of test
        reverse_result: for tests that should fail

    """

    # login
    manager.login_selenium_user(user)

    # go to page
    url = manager.base_url + reverse(
        "organisations:club_menu", kwargs={"club_id": club_id}
    )
    manager.driver.get(url)

    # Get club name
    club_name = manager.driver.find_elements_by_id("t_club_name")

    # Check for club
    ok = club_name[0].text == expected_club_name if len(club_name) > 0 else False

    new_ok = not ok if reverse_result else ok
    manager.save_results(
        status=new_ok,
        test_name=test_name,
        output=f"Visited club menu for club_id={club_id} ({url}). Looked for club name '{expected_club_name}'. {ok}",
        test_description=test_description,
    )


def club_menu_items(
    manager: CobaltTestManager,
    expected_tabs: list,
    test_name: str,
    test_description: str,
):
    """Common function to check which tabs a user has access to

        Initial Selenium State: On front page of Club Menu
        Final Selenium State: On front page of Club Menu

    Args:
        manager: test_manager.Manager object for interacting with system
        expected_tabs: the tabs we expect to find
        test_description: long description of test
        test_name: name of test
    """

    # Get all of the nav-links
    elements = manager.driver.find_elements_by_class_name("nav-link")

    # Find the ones with id_tab_
    tabs = []
    for element in elements:
        tab_id = element.get_attribute("id")
        if tab_id.find("id_tab_") >= 0:
            tabs.append(tab_id)

    # Check the tabs are as expected
    diffs = list(set(tabs) ^ set(expected_tabs))

    manager.save_results(
        status=not bool(diffs),
        test_name=test_name,
        output=f"Checked tabs present versus expected. Found differences: {diffs}",
        test_description=test_description,
    )


def club_menu_go_to_tab(
    manager: CobaltTestManager,
    tab: str,
    title: str,
    test_name: str,
    test_description: str,
):
    """Common function to move to the Access tab

        Initial Selenium State: On any tab of Club Menu
        Final Selenium State: On Access tab of Club Menu

    Args:
        manager: test_manager.Manager object for interacting with system
        tab: the tabs we want to go to
        title: expected H1 of tab
        test_description: long description of test
        test_name: name of test
    """

    # Click on tab
    tabs = manager.driver.find_elements_by_css_selector(
        f"#id_tab_{tab} > .material-icons"
    )
    if tabs:
        tabs[0].click()
    else:
        print("ERROR - CANNOT FIND TAB")

    # Confirm
    tab_heading = manager.driver.find_elements_by_id("t_tab_heading")

    if tab_heading:
        tab_title = tab_heading[0].text
        ok = title == tab_title
    else:
        tab_title = "Not found"
        ok = False

    manager.save_results(
        status=ok,
        test_name=test_name,
        output=f"Clicked on tab {tab}. Checked if t_tab_heading={title}. Actual value: {tab_title}. {ok}.",
        test_description=test_description,
    )


def login_and_go_to_club_menu(
    manager: CobaltTestManager,
    org_id: int,
    user: User,
    test_description: str,
    test_name: str,
    reverse_result: bool,
):
    """Login and got to the club menu

        Initial Selenium State: Doesn't matter
        Final Selenium State: On Club Menu logged in as User (if allowed)

    Args:
        manager: test_manager.Manager object for interacting with system
        org_id: club to check for
        user: User to use for test
        test_description: long description of test
        test_name: name of test
        reverse_result: for tests that should fail
    """
    # Login as user
    manager.login_selenium_user(manager.gary)

    # Go to club menu
    club = Organisation.objects.filter(org_id=org_id).first()
    url = manager.base_url + reverse(
        "organisations:club_menu", kwargs={"club_id": club.id}
    )
    manager.driver.get(url)

    club_name = manager.driver.find_elements_by_id("t_club_name")

    if club_name:
        title = club_name[0].text
        ok = True
    else:
        title = "Not found"
        ok = False

    real_ok = ok != reverse_result

    manager.save_results(
        status=real_ok,
        test_name=test_name,
        output=f"Logged in as {user.first_name}. Went to club menu and looked for club name. Got: {title}. "
        f"Outcome:{ok}. Expected outcome: {not reverse_result}.",
        test_description=test_description,
    )


def access_finance_for_club(
    manager: CobaltTestManager,
    club: Organisation,
    user: User,
    test_name: str,
    test_description: str,
    reverse_result=False,
):
    """Common function to move to the Access tab

        Initial Selenium State: Doesn't matter
        Final Selenium State: On Organisation Statement logged in as User

    Args:
        manager: test_manager.Manager object for interacting with system
        club: club to check for
        user: User to use for test
        test_description: long description of test
        test_name: name of test
        reverse_result: for tests that should fail
    """

    # Get URL for payments statement for this org
    url = reverse("payments:statement_org", kwargs={"org_id": club.id})

    # login the user
    manager.login_test_client(user)

    # Get page
    response = manager.client.get(url)

    # Look for Org in context to see if we got there
    ret = "org" in response.context

    ok = not ret if reverse_result else ret

    manager.save_results(
        status=ok,
        test_name=test_name,
        output=f"Accessed Org Statement for {club} as {user.first_name}. Successful: {ret}. Was this expected: {ok}",
        test_description=test_description,
    )
