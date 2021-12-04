import time

from organisations.tests.integration.common_functions import (
    club_menu_go_to_tab,
    login_and_go_to_club_menu,
)
from tests.test_manager import CobaltTestManagerIntegration

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


class ClubSettings:
    """Tests for club menu settings"""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager
        self.client = self.manager.client

    def a1_club_details(self):
        """Change Club Details and see what happens"""

        # Login as Colin
        login_and_go_to_club_menu(
            manager=self.manager,
            org_id=SUNSHINE_ID,
            user=self.manager.colin,
            test_description="Login as Colin and go to club menu",
            test_name="Login as Colin and go to club menu",
            reverse_result=False,
        )

        # Go to Settings tab
        club_menu_go_to_tab(
            manager=self.manager,
            tab="settings",
            title_id="t_tab_heading_settings",
            test_name=f"Go to Settings tab as Colin for {club_names[SUNSHINE_ID]}",
            test_description="Starting from the dashboard of Club Menu we click on the Settings tab "
            "and confirm that we get there.",
        )

        # Change club name
        self.manager.driver.find_element_by_id("id_name").send_keys("fish")
        self.manager.driver.find_element_by_name("Save").click()

        self.manager.save_results(
            status=True,
            output="Changed club name, no errors",
            test_name=f"Colin changes the name of {club_names[SUNSHINE_ID]}",
            test_description=f"Colin goes to the Settings tab and changes the name of {club_names[SUNSHINE_ID]}. "
            f"(The data for this club was rubbish to begin with).",
        )

        # Check we get errors on screen (mismatch with MPC)
        ok = bool(self.manager.selenium_wait_for("t_reload_mpc"))
        self.manager.save_results(
            status=ok,
            output=f"Checked for MPC reload to be found on page. {ok}",
            test_name=f"Check data is out of step with MPC for {club_names[SUNSHINE_ID]}",
            test_description=f"Colin is on the Settings tab for {club_names[SUNSHINE_ID]}. "
            f"The data for this club was is out of step with the MPC so we expect to see a "
            f"button to re-sync it.",
        )

        # Fix errors if we can
        if ok:
            self.manager.selenium_wait_for("t_reload_mpc").click()
            # give it time to go away
            time.sleep(2)
            ok = not bool(self.manager.selenium_wait_for("t_reload_mpc", timeout=2))
            self.manager.save_results(
                status=ok,
                output=f"Checked for MPC reload to be missing from page. {ok}",
                test_name=f"Colin re-syncs data with MPC for {club_names[SUNSHINE_ID]}",
                test_description=f"Colin is on the Settings tab for {club_names[SUNSHINE_ID]}. "
                f"The data is out of step with the MPC. Colin clicks on the re-sync button. "
                f"We check that the resync button now disappears.",
            )

    def a2_membership_types(self):
        """Test club membership types"""

        # We are on the settings tab already. Go to membership types
        self.manager.selenium_wait_for("t_settings_membership_types").click()
        self.manager.save_results(
            status=True,
            output="Clicked on Membership Type sub-tab.",
            test_name=f"Colin goes to Membership Types for {club_names[SUNSHINE_ID]}",
            test_description=f"Colin is on the Settings tab for {club_names[SUNSHINE_ID]}. "
            f"He clicks on Membership Types.",
        )

        # click on Standard !!!! Assumes Standard is pk=7, will fail if other data is added before
        standard = self.manager.selenium_wait_for("id_membership-btn-7")

        if not standard:
            self.manager.save_results(
                status=False,
                output="Clicked on Membership Type sub-tab, expected to find Standard as a membership type with"
                "id=7. Not found. ALL SUBSEQUENT TESTS WILL FAIL. ABORTING.",
                test_name=f"Colin looks for Membership Type = Standard for {club_names[SUNSHINE_ID]}",
                test_description=f"Colin is on the Settings tab for {club_names[SUNSHINE_ID]}. "
                f"He clicks on Membership Types and then on Standard.",
            )
            return

        standard.click()

        annual_fee = self.manager.selenium_wait_for("id_annual_fee")
        annual_fee.clear()
        annual_fee.send_keys("77.31")

        self.manager.selenium_wait_for("t_mtype_save").click()

        time.sleep(1)

        annual_fee = self.manager.selenium_wait_for("id_annual_fee")
        new_val = annual_fee.get_attribute("value")
        ok = bool(new_val == "77.31")

        self.manager.save_results(
            status=ok,
            output=f"Changed annual fee to '77.31'. Value became '{new_val}'",
            test_name=f"Colin changes annual fee for Standard membership for {club_names[SUNSHINE_ID]}",
            test_description=f"Colin changes the annual fee for Standard membership for {club_names[SUNSHINE_ID]}. "
            f"We check that the value updates correctly.",
        )
