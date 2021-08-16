import time

from django.urls import reverse
from selenium.common.exceptions import StaleElementReferenceException

from accounts.tests.common_functions import register_user
from organisations.models import Organisation
from organisations.tests.common_functions import (
    access_club_menu,
    club_menu_items,
    club_menu_go_to_tab,
    access_finance_for_club,
    set_rbac_status_as_user,
)
from tests.common_functions import cobalt_htmx_user_search
from tests.test_manager import CobaltTestManager

# TODO: See if these constants can be centrally stored

# State id numbers
NSW = 3
QLD = 5

# Org org_id numbers
CANBERRA_ID = 1851
TRUMPS_ID = 2259
SUNSHINE_ID = 4860
WAVERLEY_ID = 3480

# Org names
club_names = {
    CANBERRA_ID: "Canberra Bridge Club Inc",  # ACT
    TRUMPS_ID: "Trumps Bridge Centre",  # NSW
    SUNSHINE_ID: "Sunshine Coast Contract Bridge Club Inc",  # QLD
    WAVERLEY_ID: "Waverley Bridge Club",  # VIC
}


class ClubLevelAdmin:
    """Tests for club level admin. These are the changes that club admins will do
    regularly. State and system admins should also be able to do this.

    """

    NSW = 3
    QLD = 5

    def __init__(self, manager: CobaltTestManager):
        self.manager = manager
        self.client = self.manager.client

    def a1_access_club_menu(self):
        """Check who can access the club menu"""

        club = Organisation.objects.filter(org_id=TRUMPS_ID).first()

        # Eric - Trumps - No Access
        access_club_menu(
            manager=self.manager,
            user=self.manager.eric,
            club_id=club.id,
            expected_club_name=club_names[TRUMPS_ID],
            test_name=f"Check that Eric can't access the club menu for {club_names[TRUMPS_ID]}",
            test_description=f"Go to the club menu page for {club_names[TRUMPS_ID]} "
            f"(org_id={TRUMPS_ID}) as Eric who shouldn't have access.",
            reverse_result=True,
        )

        # Debbie - Trumps - Access
        access_club_menu(
            manager=self.manager,
            user=self.manager.debbie,
            club_id=club.id,
            expected_club_name=club_names[TRUMPS_ID],
            test_name=f"Check that Debbie can access the club menu for {club_names[TRUMPS_ID]}",
            test_description=f"Go to the club menu page for {club_names[TRUMPS_ID]} "
            f"(org_id={TRUMPS_ID}) as Debbie (club secretary)",
        )

        # Debbie - Check Tabs
        expected_tabs = [
            "id_tab_dashboard",
            "id_tab_members",
            "id_tab_congress",
            "id_tab_results",
            "id_tab_comms",
            "id_tab_access",
            "id_tab_settings",
            "id_tab_finance",
            "id_tab_forums",
        ]

        club_menu_items(
            manager=self.manager,
            expected_tabs=expected_tabs,
            test_name=f"Check tabs for Debbie for {club_names[TRUMPS_ID]}",
            test_description=f"Go to the club menu page for {club_names[TRUMPS_ID]} "
            f"(org_id={TRUMPS_ID}) as Debbie. Check tabs are {expected_tabs}",
        )

    def a2_rbac_basic_user_admin(self):
        """Test user admin for Basic RBAC"""

        # We are Debbie - add a user

        # Go to Access tab
        club_menu_go_to_tab(
            manager=self.manager,
            tab="access",
            title="Staff Access",
            test_name=f"Go to Access tab as Debbie for {club_names[TRUMPS_ID]}",
            test_description="Starting from the dashboard of Club Menu we click on the Access tab "
            "and confirm that we get there.",
        )

        # Use search to add Eric
        cobalt_htmx_user_search(
            manager=self.manager,
            search_button_id="id_search_button",
            user_system_id="104",
            search_id="",
        )

        # Check Eric is there
        ok = self.manager.selenium_wait_for_text("access", "Eric")

        if ok:
            output = "Added Eric through search and he appeared in the 'access' div afterwards. Pass."
        else:
            output = "Tried added Eric through search but he didn't appear in the 'access' div afterwards. Fail."

        self.manager.save_results(
            status=ok,
            output=output,
            test_name=f"Debbie adds Eric as an admin to Basic RBAC for {club_names[TRUMPS_ID]}",
            test_description=f"Debbie goes to Access tab for {club_names[TRUMPS_ID]} and uses the HTMX user "
            f"search to add Eric as an Admin using Basic RBAC. We then look for Eric to "
            f"appear on the page.",
        )

        # Use search to add Fiona
        cobalt_htmx_user_search(
            manager=self.manager,
            search_button_id="id_search_button",
            user_system_id="105",
            search_id="",
        )

        # Check Fiona is there
        ok = self.manager.selenium_wait_for_text("access", "Fiona")

        if ok:
            output = "Added Fiona through search and she appeared in the 'access' div afterwards. Pass."
        else:
            output = "Tried added Fiona through search but she didn't appear in the 'access' div afterwards. Fail."

        self.manager.save_results(
            status=ok,
            output=output,
            test_name=f"Debbie adds Fiona as an admin to Basic RBAC for {club_names[TRUMPS_ID]}",
            test_description=f"Debbie goes to Access tab for {club_names[TRUMPS_ID]} and uses the HTMX user "
            f"search to add Fiona as an Admin using Basic RBAC. We then look for Fiona to "
            f"appear on the page.",
        )

        # Delete Fiona
        try:
            self.manager.driver.find_element_by_id(
                f"id_delete_user_{self.manager.fiona.id}"
            ).click()
        except StaleElementReferenceException:
            self.manager.driver.find_element_by_id(
                f"id_delete_user_{self.manager.fiona.id}"
            ).click()

        self.manager.selenium_wait_for_clickable(
            f"id_delete_button_{self.manager.fiona.id}"
        ).click()

        # Wait for screen - will have betty on it
        self.manager.selenium_wait_for_text("access", "Betty")
        # Check for Fiona
        ok = self.manager.driver.find_element_by_id("access").text.find("Fiona") == -1

        if ok:
            output = "Fiona no longer on page. Pass."
        else:
            output = "Fiona still on page. Fail."

        self.manager.save_results(
            status=ok,
            output=output,
            test_name=f"Debbie deletes Fiona as an admin from Basic RBAC for {club_names[TRUMPS_ID]}",
            test_description=f"Debbie goes to Access tab for {club_names[TRUMPS_ID]} and deletes Fiona "
            f"as an Admin using Basic RBAC. We then look for Fiona to "
            f"appear on the page.",
        )

        expected_tabs = [
            "id_tab_dashboard",
            "id_tab_members",
            "id_tab_congress",
            "id_tab_results",
            "id_tab_comms",
            "id_tab_access",
            "id_tab_settings",
            "id_tab_finance",
            "id_tab_forums",
        ]

        club_menu_items(
            manager=self.manager,
            expected_tabs=expected_tabs,
            test_name=f"Check tabs for Eric for {club_names[TRUMPS_ID]}",
            test_description=f"Go to the club menu page for {club_names[TRUMPS_ID]} "
            f"(org_id={TRUMPS_ID}) as Eric. Check tabs are {expected_tabs}",
        )

        # Access Finance info for Trumps as Alan

        trumps = Organisation.objects.filter(org_id=TRUMPS_ID).first()

        access_finance_for_club(
            manager=self.manager,
            club=trumps,
            user=self.manager.colin,
            test_name=f"Access finance info for {trumps} as Colin",
            test_description=f"Colin tries to access the club bank statement for {trumps}. This should fail "
            f"as he doesn't have access to it.",
            reverse_result=True,
        )

        # Access Finance info for Trumps as Eric

        access_finance_for_club(
            manager=self.manager,
            club=trumps,
            user=self.manager.eric,
            test_name=f"Access finance info for {trumps} as Eric",
            test_description=f"Eric tries to access the club bank statement for {trumps}. This should work "
            f"as he has access to it.",
            reverse_result=False,
        )

        # Register a user
        register_user(self.manager, "620254")

    def a3_rbac_advanced_user_admin(self):
        """user admin tests for advanced RBAC"""

        # Advanced users - check tabs
        self.manager.login_user(self.manager.colin)

        # We need an advanced RBAC club but stupid Colin changed his, change it back
        # Colin - Sunshine - Advanced = Yes
        set_rbac_status_as_user(
            manager=self.manager,
            user=self.manager.colin,
            club_org_id=SUNSHINE_ID,
            new_status="Advanced",
            test_name="Re-Check Colin can change RBAC status to Advanced for a Club in his state.",
            test_description=f"""Colin tries to change RBAC status for {club_names[SUNSHINE_ID]}
                                 from Basic to Advanced. Should work. We already tested this but we need
                                 it changed to advanced for the next tests.""",
            reverse_result=False,
        )

        # Go to club menu
        club = Organisation.objects.filter(org_id=SUNSHINE_ID).first()
        url = self.manager.base_url + reverse(
            "organisations:club_menu", kwargs={"club_id": club.id}
        )
        self.manager.driver.get(url)

        # Go to Access tab
        club_menu_go_to_tab(
            manager=self.manager,
            tab="access",
            title="Staff Access",
            test_name=f"Go to Access tab as Colin for {club_names[SUNSHINE_ID]}",
            test_description="Starting from the dashboard of Club Menu we click on the Access tab "
            "and confirm that we get there.",
        )

        # Use search to add Fiona
        cobalt_htmx_user_search(
            manager=self.manager,
            search_button_id="id_access_advanced_add_payments_view",
            user_system_id="105",
            search_id="payments_view",
        )

        self.manager.save_results(
            status=True,
            test_name="Colin adds Fiona to Payments View",
            test_description=f"Colin uses the search to add Fiona as an user to payments view "
            f"for {club_names[SUNSHINE_ID]}",
            output="This seemed to work. True",
        )

        # Login as Fiona and check tabs
        self.manager.login_test_client(self.manager.fiona)

        expected_tabs = [
            "id_tab_dashboard",
            "id_tab_members",
            "id_tab_congress",
            "id_tab_results",
            "id_tab_comms",
            "id_tab_access",
            "id_tab_settings",
            "id_tab_finance",
            "id_tab_forums",
        ]

        club_menu_items(
            manager=self.manager,
            expected_tabs=expected_tabs,
            test_name=f"Check tabs for Fiona for {club_names[SUNSHINE_ID]}",
            test_description=f"Login as Fiona and go to the club menu page for {club_names[SUNSHINE_ID]} "
            f"(org_id={SUNSHINE_ID})Check tabs are {expected_tabs}",
        )


# TODO: Check adding users basic (before and after access check)
# TODO: Advanced - check only the right tabs are added
# TODO: Check calling add view directly
# TODO: Delete users basic
# TODO: Delete users advanced
# TODO: Delete admins advanced
# TODO: Check menu item appears properly
# TODO: Multiple clubs
#
