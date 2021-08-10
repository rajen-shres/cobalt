from organisations.models import Organisation
from organisations.tests.common_functions import access_club_menu, club_menu_items
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
        self.alan = self.manager.test_user
        self.betty = self.manager.get_user("101")
        self.colin = self.manager.get_user("102")
        self.debbie = self.manager.get_user("103")
        self.eric = self.manager.get_user("104")

    def a1_access_club_menu(self):
        """Check who can access the club menu"""

        club = Organisation.objects.filter(org_id=TRUMPS_ID).first()

        # Eric - Trumps - No Access
        access_club_menu(
            manager=self.manager,
            user=self.eric,
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
            user=self.debbie,
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
        ]

        club_menu_items(
            manager=self.manager,
            expected_tabs=expected_tabs,
            test_name=f"Check tabs for Debbie for {club_names[TRUMPS_ID]}",
            test_description=f"Go to the club menu page for {club_names[TRUMPS_ID]} "
            f"(org_id={TRUMPS_ID}) as Debbie. Check tabs are {expected_tabs}",
        )
