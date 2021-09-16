import time

from organisations.tests.common_functions import (
    club_menu_go_to_tab,
    login_and_go_to_club_menu,
)
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


class ClubComms:
    """Tests for club communications"""

    def __init__(self, manager: CobaltTestManager):
        self.manager = manager
        self.client = self.manager.client

    def a1_comms_tags(self):
        """Do things with tags"""

        # Login as Colin
        login_and_go_to_club_menu(
            manager=self.manager,
            org_id=SUNSHINE_ID,
            user=self.manager.colin,
            test_description="Login as Colin and go to club menu",
            test_name="Login as Colin and go to club menu",
            reverse_result=False,
        )

        # Go to Comms tab
        club_menu_go_to_tab(
            manager=self.manager,
            tab="comms",
            title_id="t_tab_heading_comms",
            test_name=f"Go to comms tab as Colin for {club_names[SUNSHINE_ID]}",
            test_description="Starting from the dashboard of Club Menu we click on the Communications tab "
            "and confirm that we get there.",
        )

        # Add a tag
        self.manager.selenium_wait_for_clickable("t_comms_tab_tags").click()
        self.manager.selenium_wait_for_clickable("id_tag_name").send_keys(
            "Grumpy Buggers"
        )
        self.manager.selenium_wait_for_clickable("id_tags_add_tag").click()

        self.manager.save_results(
            status=True,
            output=f"Added a new tag for {club_names[SUNSHINE_ID]} as Colin (admin).",
            test_name=f"Colin adds tag 'Grumpy Buggers' for {club_names[SUNSHINE_ID]}",
            test_description=f"Colin goes to the comms tab for {club_names[SUNSHINE_ID]}. "
            f"He then clicks on tags and adds a new one.",
        )

        # Add a tag again
        self.manager.selenium_wait_for_text("Grumpy", "id_panel_comms")
        self.manager.selenium_wait_for_clickable("id_tag_name").send_keys("Nice People")
        self.manager.selenium_wait_for_clickable("id_tags_add_tag").click()

        self.manager.save_results(
            status=True,
            output=f"Added a new tag for {club_names[SUNSHINE_ID]} as Colin (admin).",
            test_name=f"Colin adds tag 'Nice People' for {club_names[SUNSHINE_ID]}",
            test_description=f"Colin goes to the comms tab for {club_names[SUNSHINE_ID]}. "
            f"He then clicks on tags and adds a new one.",
        )

        # Add a tag again again
        self.manager.selenium_wait_for_text("Nice People", "id_panel_comms")
        self.manager.selenium_wait_for_clickable("id_tag_name").send_keys("Geniuses")
        self.manager.selenium_wait_for_clickable("id_tags_add_tag").click()

        self.manager.save_results(
            status=True,
            output=f"Added a new tag for {club_names[SUNSHINE_ID]} as Colin (admin).",
            test_name=f"Colin adds tag 'Geniuses' for {club_names[SUNSHINE_ID]}",
            test_description=f"Colin goes to the comms tab for {club_names[SUNSHINE_ID]}. "
            f"He then clicks on tags and adds a new one.",
        )
