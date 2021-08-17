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
SUNSHINE_ID = 4860
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

    def __init__(self, manager: CobaltTestManager):
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
            title="Club Settings",
            test_name=f"Go to Settings tab as Colin for {club_names[SUNSHINE_ID]}",
            test_description="Starting from the dashboard of Club Menu we click on the Settings tab "
            "and confirm that we get there.",
        )
