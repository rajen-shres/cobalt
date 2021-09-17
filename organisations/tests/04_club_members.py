import time

from organisations.tests.common_functions import (
    club_menu_go_to_tab,
    login_and_go_to_club_menu,
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
SUNSHINE_ID = 4680
WAVERLEY_ID = 3480

# Org names
club_names = {
    CANBERRA_ID: "Canberra Bridge Club Inc",  # ACT
    TRUMPS_ID: "Trumps Bridge Centre",  # NSW
    SUNSHINE_ID: "Sunshine Coast Contract Bridge Club Inc",  # QLD
    WAVERLEY_ID: "Waverley Bridge Club",  # VIC
}


class ClubMembers:
    """Tests for club menu members. Some of these tests connect to the MPC so data may change over time."""

    def __init__(self, manager: CobaltTestManager):
        self.manager = manager
        self.client = self.manager.client

    def a1_import_members(self):
        """Import Members to this club"""

        # Login as Colin (no update access to members)
        login_and_go_to_club_menu(
            manager=self.manager,
            org_id=SUNSHINE_ID,
            user=self.manager.colin,
            test_description="Login as Colin and go to club menu. Colin doesn't have update access to members.",
            test_name=f"Login as Colin and go to club menu for {club_names[SUNSHINE_ID]}",
            reverse_result=False,
        )

        # Go to Members tab
        club_menu_go_to_tab(
            manager=self.manager,
            tab="members",
            title_id="id_member_list_tab",
            test_name=f"Go to Members tab as Colin for {club_names[SUNSHINE_ID]}",
            test_description="Starting from the dashboard of Club Menu we click on the Members tab "
            "and confirm that we get there.",
        )

        ok = not bool(self.manager.selenium_wait_for("t_member_tab_add", timeout=2))

        self.manager.save_results(
            status=ok,
            output=f"Clicked on Membership tab for {club_names[SUNSHINE_ID]} as Colin. Shouldn't get the Add sub-tab. "
            f"Outcome: {ok}",
            test_name=f"Colin cannot add members for {club_names[SUNSHINE_ID]}",
            test_description=f"Colin goes to the members tab for {club_names[SUNSHINE_ID]}. "
            f"He shouldn't see Add as an option as he doesn't have access.",
        )

        # Login as Eric
        login_and_go_to_club_menu(
            manager=self.manager,
            org_id=SUNSHINE_ID,
            user=self.manager.eric,
            test_description="Login as Eric (admin) and go to club menu",
            test_name="Login as Eric and go to club menu",
            reverse_result=False,
        )

        # Go to Members tab
        club_menu_go_to_tab(
            manager=self.manager,
            tab="members",
            title_id="id_member_list_tab",
            test_name=f"Go to Members tab as Eric for {club_names[SUNSHINE_ID]}",
            test_description="Starting from the dashboard of Club Menu we click on the Members tab "
            "and confirm that we get there.",
        )

        ok = bool(self.manager.selenium_wait_for("t_member_tab_add"))

        self.manager.save_results(
            status=ok,
            output=f"Clicked on Membership tab for {club_names[SUNSHINE_ID]} as Eric (admin). Should get the Add sub-tab. "
            f"Outcome: {ok}",
            test_name=f"Eric can add members for {club_names[SUNSHINE_ID]}",
            test_description=f"Eric goes to the members tab for {club_names[SUNSHINE_ID]}. "
            f"He should see Add as an option as he does have access.",
        )

        # Import from MPC
        # Click Add
        self.manager.selenium_wait_for("t_member_tab_add").click()
        # Click MPC Import
        self.manager.selenium_wait_for("t_mpc_import").click()
        # Click Save
        self.manager.selenium_wait_for("t_mpc_import_save").click()

        ok = bool(self.manager.selenium_wait_for_text("Import Complete", "members"))

        self.manager.save_results(
            status=ok,
            output=f"Ran MPC import for {club_names[SUNSHINE_ID]} as Eric (admin). Got 'Import Complete'"
            f"Outcome: {ok}",
            test_name=f"Eric imports members from MPC for {club_names[SUNSHINE_ID]}",
            test_description=f"Eric imports members from MPC for {club_names[SUNSHINE_ID]}. "
            f"He should be able to do this successfully.",
        )

    def a2_add_edit_delete_club_members(self):

        # We are on the members tab already

        # Click Add
        self.manager.selenium_wait_for("t_member_tab_add").click()
        # Click Add Member
        self.manager.selenium_wait_for("t_member_add_individual_member").click()

        # Search for Betty
        cobalt_htmx_user_search(
            manager=self.manager,
            search_button_id="id_add_member_item",
            user_system_id=self.manager.betty.system_number,
            search_id="add_member",
        )

        # Click Save
        self.manager.selenium_wait_for_clickable("t_member_add_member_button").click()

        ok = bool(
            self.manager.selenium_wait_for_text(
                "Betty Bunting added as a member", "members"
            )
        )

        self.manager.save_results(
            status=ok,
            output=f"Eric added Betty as a member to {club_names[SUNSHINE_ID]}."
            f"Outcome: {ok}",
            test_name=f"Eric adds Betty as member of {club_names[SUNSHINE_ID]}",
            test_description=f"Eric uses the manual entry screen for {club_names[SUNSHINE_ID]}. "
            f"to add Betty as a member.",
        )

        # Now add unregistered - We need to use a real user!!! Use Ian Thomson

        # Click Add
        self.manager.selenium_wait_for("t_member_tab_add").click()
        # Click Add Un Reg
        self.manager.selenium_wait_for("t_member_add_individual_un_reg").click()

        # Enter system number
        self.manager.selenium_wait_for("id_system_number").send_keys("148911")

        # Enter email
        self.manager.selenium_wait_for("id_mpc_email").send_keys("a@b.com")

        # Dunno.
        time.sleep(2)

        # Click Save
        self.manager.selenium_wait_for_clickable("t_member_add_un_reg_button").click()

        ok = bool(self.manager.selenium_wait_for_text("User added.", "members"))

        self.manager.save_results(
            status=ok,
            output=f"Eric added Ian Thomson as an unregistered member to {club_names[SUNSHINE_ID]}. "
            f"Outcome: {ok}",
            test_name=f"Eric adds Ian Thomson as member of {club_names[SUNSHINE_ID]}",
            test_description=f"Eric uses the manual entry screen for {club_names[SUNSHINE_ID]}. "
            f"to add Ian Thomson (148911) as an unregistered member. We unfortunately need to "
            f"use a real person for this or the lookup with the MPC won't work.",
        )

        # Edit Member

        # Click List - easier to go to Members tab again
        club_menu_go_to_tab(
            manager=self.manager,
            tab="members",
            title_id="id_member_list_tab",
            test_name=f"Go to Members tab as Eric for {club_names[SUNSHINE_ID]}",
            test_description="Return to the Members tab as Eric.",
        )

        # Click on Betty
        self.manager.selenium_wait_for(f"t_edit_member_{self.manager.betty.id}").click()

        # Click on Membership Type
        self.manager.selenium_wait_for("id_membership_type").click()

        # click on Youth
        self.manager.driver.find_element_by_xpath("//option[. = 'Youth']").click()

        # Save
        self.manager.driver.find_element_by_name("save").click()

        # Look for success

        ok = bool(
            self.manager.selenium_wait_for_text("Betty Bunting updated", "members")
        )

        self.manager.save_results(
            status=ok,
            output=f"Eric edited Betty, a member of {club_names[SUNSHINE_ID]}. "
            f"Outcome: {ok}",
            test_name=f"Eric edits Betty as member of {club_names[SUNSHINE_ID]}.",
            test_description=f"Eric edits Betty, a member of for {club_names[SUNSHINE_ID]}. "
            f"Changes membership type to 'Youth'",
        )

        # Cancel Membership

        # Click on Betty
        self.manager.selenium_wait_for(f"t_edit_member_{self.manager.betty.id}").click()

        # Wait for Cancel button
        self.manager.selenium_wait_for_clickable("id_delete_user_1").click()

        # Click on Confirm
        self.manager.selenium_wait_for_clickable("id_delete_button_memdel").click()

        # Check for message
        ok = bool(
            self.manager.selenium_wait_for_text(
                "Betty Bunting membership deleted", "members"
            )
        )

        self.manager.save_results(
            status=ok,
            output=f"Eric cancelled Betty's membership of {club_names[SUNSHINE_ID]}. "
            f"Outcome: {ok}",
            test_name=f"Eric cancels Betty as member of {club_names[SUNSHINE_ID]}.",
            test_description=f"Eric cancels Betty's membership of {club_names[SUNSHINE_ID]}. ",
        )
