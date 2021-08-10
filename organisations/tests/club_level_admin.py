import time
from pprint import pprint

from django.urls import reverse

from organisations.models import Organisation
from organisations.tests.common_functions import access_club_menu
from tests.test_manager import CobaltTestManager

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

    def __init__(self, manager: CobaltTestManager):
        self.manager = manager
        self.client = self.manager.client
        self.alan = self.manager.test_user
        self.betty = self.manager.get_user("101")
        self.colin = self.manager.get_user("102")
        self.debbie = self.manager.get_user("103")

        print("init")

    def a1_access_club_menu(self):
        """Check who can access the club menu"""

        print("running")

        club = Organisation.objects.filter(org_id=TRUMPS_ID).first()

        print(club)

        access_club_menu(
            manager=self.manager,
            user=self.debbie,
            club_id=club.id,
            test_name="ddd",
            test_description="fff",
        )

        print("b2")

        access_club_menu(
            manager=self.manager,
            user=self.debbie,
            club_id=club.id,
            test_name="ddd",
            test_description="fff",
        )

        print("back")
