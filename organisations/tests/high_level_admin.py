from pprint import pprint

from django.urls import reverse

from organisations.models import Organisation
from organisations.tests.common_functions import (
    add_club,
    confirm_club_rbac_status,
    set_rbac_status_as_user,
    change_rbac_status_as_user,
)
from rbac.core import rbac_user_has_role
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


class OrgHighLevelAdmin:
    """Tests for higher level admin functions such as creating clubs and setting up RBAC.

    These actions generally require state or national body level admin rights.

    Club admins can also change the RBAC settings for their club which is also tested here.

    Alan Admin has the role "orgs.admin.edit" and can add clubs for any state.
    Betty Bunting has "orgs.state.3" - NSW.
    Colin Corgy has "orgs.state.5" - QLD.

    """

    def __init__(self, manager: CobaltTestManager):
        self.manager = manager
        self.client = self.manager.client
        self.alan = self.manager.test_user
        self.betty = self.manager.get_user("101")
        self.colin = self.manager.get_user("102")
        self.debbie = self.manager.get_user("103")

    def a1_admin_add_club(self):

        # Check access
        aa_global_role = rbac_user_has_role(self.alan, "orgs.admin.edit")
        bb_global_role = rbac_user_has_role(self.betty, "orgs.admin.edit")
        cc_global_role = rbac_user_has_role(self.colin, "orgs.admin.edit")

        aa_nsw_role = rbac_user_has_role(self.alan, f"orgs.state.{NSW}.edit")
        bb_nsw_role = rbac_user_has_role(self.betty, f"orgs.state.{NSW}.edit")
        cc_nsw_role = rbac_user_has_role(self.colin, f"orgs.state.{NSW}.edit")

        aa_qld_role = rbac_user_has_role(self.alan, f"orgs.state.{QLD}.edit")
        bb_qld_role = rbac_user_has_role(self.betty, f"orgs.state.{QLD}.edit")
        cc_qld_role = rbac_user_has_role(self.colin, f"orgs.state.{QLD}.edit")

        ok = True

        if not aa_global_role:
            ok = False
        if bb_global_role:
            ok = False
        if cc_global_role:
            ok = False

        if aa_nsw_role:
            ok = False
        if not bb_nsw_role:
            ok = False
        if cc_nsw_role:
            ok = False

        if aa_qld_role:
            ok = False
        if bb_qld_role:
            ok = False
        if not cc_qld_role:
            ok = False

        self.manager.save_results(
            status=ok,
            test_name="Check RBAC roles for AA, BB, CC",
            test_description="Test the starting RBAC roles for Alan, Betty and Colin. Alan should be a global admin, Betty should be an admin for NSW and Colin should be an admin for QLD.",
        )

        ################################################

        # Check orgs don't exist before we start
        ns_ok = not Organisation.objects.filter(org_id=CANBERRA_ID).exists()
        tr_ok = not Organisation.objects.filter(org_id=TRUMPS_ID).exists()
        su_ok = not Organisation.objects.filter(org_id=SUNSHINE_ID).exists()
        wa_ok = not Organisation.objects.filter(org_id=WAVERLEY_ID).exists()

        ok = ns_ok and tr_ok and su_ok and wa_ok

        self.manager.save_results(
            status=ok,
            test_name="Check orgs not present",
            output=f"Checking if orgs exists: {not ok}",
            test_description="Before we start we check that the organisations don't exist.",
        )

        #############################################################

        view_data = {
            "secretary": self.debbie.id,
            "name": club_names[CANBERRA_ID],
            "org_id": CANBERRA_ID,
            "club_email": "a@b.com",
            "club_website": "www.com",
            "address1": "20 Street Avenue",
            "suburb": "Wombleville",
            "state": "ACT",
            "postcode": 1000,
        }

        # Alan add a club - should work
        add_club(self.manager, self.alan, view_data)

        # Betty add a club - should work
        view_data["org_id"] = TRUMPS_ID
        view_data["state"] = "NSW"
        view_data["name"] = club_names[TRUMPS_ID]
        add_club(self.manager, self.betty, view_data)

        # Colin add a club - should work
        view_data["org_id"] = SUNSHINE_ID
        view_data["state"] = "QLD"
        view_data["name"] = club_names[SUNSHINE_ID]
        add_club(self.manager, self.colin, view_data)

        # Betty add a club - should fail
        view_data["org_id"] = WAVERLEY_ID
        view_data["state"] = "VIC"
        view_data["name"] = club_names[WAVERLEY_ID]
        add_club(self.manager, self.betty, view_data, reverse)

        # Colin add a club - should fail
        add_club(self.manager, self.colin, view_data, reverse)

    def a2_admin_change_rbac_configuration(self):
        """Changing RBAC configuration for a club"""

        # Check initial state
        confirm_club_rbac_status(
            self.manager,
            CANBERRA_ID,
            "Not Set Up",
            f"Check {club_names[CANBERRA_ID]} not set up",
            "Before we start, check that RBAC is not set up for this club",
        )
        confirm_club_rbac_status(
            self.manager,
            TRUMPS_ID,
            "Not Set Up",
            f"Check {club_names[TRUMPS_ID]} not set up",
            "Before we start, check that RBAC is not set up for this club",
        )
        confirm_club_rbac_status(
            self.manager,
            SUNSHINE_ID,
            "Not Set Up",
            f"Check {club_names[SUNSHINE_ID]} not set up",
            "Before we start, check that RBAC is not set up for this club",
        )

        # Try some that shouldn't work

        # Betty - Sunshine - Basic = No
        set_rbac_status_as_user(
            manager=self.manager,
            user=self.betty,
            club_org_id=SUNSHINE_ID,
            new_status="Basic",
            test_name="Check Betty can't change RBAC status to Basic for another state's club",
            test_description=f"""Betty tries to change RBAC status for {club_names[SUNSHINE_ID]}
                                 from unset to Basic. Should fail.""",
            reverse_result=True,
        )

        # Colin - Trumps - Basic = No
        set_rbac_status_as_user(
            manager=self.manager,
            user=self.colin,
            club_org_id=TRUMPS_ID,
            new_status="Basic",
            test_name="Check Colin can't change RBAC status to Basic for another state's club",
            test_description=f"Colin tries to change RBAC status for {club_names[TRUMPS_ID]} from unset to Basic. Should fail.",
            reverse_result=True,
        )

        # Debbie - Canberra - Basic = No
        set_rbac_status_as_user(
            manager=self.manager,
            user=self.debbie,
            club_org_id=CANBERRA_ID,
            new_status="Basic",
            test_name="Check Debbie can't change RBAC status to Basic for a club despite being secretary",
            test_description=f"""Debbie tries to change RBAC status for {club_names[CANBERRA_ID]}
                                 from unset to Basic. Should fail. Debbie is the club secretary, but we haven't given
                                 her any RBAC access yet.""",
            reverse_result=True,
        )

        # Betty - Sunshine - Advanced = No
        set_rbac_status_as_user(
            manager=self.manager,
            user=self.betty,
            club_org_id=SUNSHINE_ID,
            new_status="Advanced",
            test_name="Check Betty can't change RBAC status to Advanced for another state's club",
            test_description=f"Betty tries to change RBAC status for {club_names[SUNSHINE_ID]} to Advanced. Should fail.",
            reverse_result=True,
        )

        # Colin - Canberra - Advanced = No
        set_rbac_status_as_user(
            manager=self.manager,
            user=self.colin,
            club_org_id=CANBERRA_ID,
            new_status="Advanced",
            test_name="Check Colin can't change RBAC status to Advanced for another state's club",
            test_description=f"Colin tries to change RBAC status for {club_names[CANBERRA_ID]} to Advanced. Should fail.",
            reverse_result=True,
        )

        # Try some that should work

        # Betty - Trumps - Basic = Yes
        set_rbac_status_as_user(
            manager=self.manager,
            user=self.betty,
            club_org_id=TRUMPS_ID,
            new_status="Basic",
            test_name="Check Betty can change RBAC status to Basic for a Club in her state.",
            test_description=f"""Betty tries to change RBAC status for {club_names[TRUMPS_ID]}
                                 from unset to Basic. Should work.""",
            reverse_result=False,
        )

        # Colin - Sunshine - Advanced = Yes
        set_rbac_status_as_user(
            manager=self.manager,
            user=self.colin,
            club_org_id=SUNSHINE_ID,
            new_status="Advanced",
            test_name="Check Colin can change RBAC status to Advanced for a Club in his state.",
            test_description=f"""Colin tries to change RBAC status for {club_names[SUNSHINE_ID]}
                                 from unset to Advanced. Should work.""",
            reverse_result=False,
        )

        # Change RBAC status tests

        # Betty - Sunshine - To Basic = No
        change_rbac_status_as_user(
            manager=self.manager,
            user=self.betty,
            club_org_id=SUNSHINE_ID,
            new_status="Basic",
            test_name="Check Betty can't change RBAC status to Basic from Advanced for a Club not in her state.",
            test_description=f"""Betty tries to change RBAC status for {club_names[SUNSHINE_ID]}
                                 from Advanced to Basic. Should fail.""",
            reverse_result=True,
        )

        # Colin - Canberra - To Advanced = No
        change_rbac_status_as_user(
            manager=self.manager,
            user=self.colin,
            club_org_id=CANBERRA_ID,
            new_status="Advanced",
            test_name="Check Colin can't change RBAC status to Advanced from Basic for a Club not in his state.",
            test_description=f"""Colin tries to change RBAC status for {club_names[CANBERRA_ID]}
                                 from Basic to Advanced. Should fail.""",
            reverse_result=True,
        )

        # Betty - Trumps - To Advanced = Yes
        change_rbac_status_as_user(
            manager=self.manager,
            user=self.betty,
            club_org_id=TRUMPS_ID,
            new_status="Advanced",
            test_name="Check Betty can change RBAC status to Advanced from Basic for a Club in her state.",
            test_description=f"""Betty tries to change RBAC status for {club_names[TRUMPS_ID]}
                                 from Basic to Advanced. Should work.""",
            reverse_result=False,
        )

        # Colin - Sunshine - To Basic = Yes
        change_rbac_status_as_user(
            manager=self.manager,
            user=self.colin,
            club_org_id=SUNSHINE_ID,
            new_status="Basic",
            test_name="Check Colin can change RBAC status to Basic from Advanced for a Club in his state.",
            test_description=f"""Colin tries to change RBAC status for {club_names[SUNSHINE_ID]}
                                 from Advanced to Basic. Should work.""",
            reverse_result=False,
        )

        # Once RBAC is set up Debbie should be able to change things

        # Debbie - Trumps - To Basic = Yes
        change_rbac_status_as_user(
            manager=self.manager,
            user=self.debbie,
            club_org_id=TRUMPS_ID,
            new_status="Basic",
            test_name="Check Debbie (club secretary) can change RBAC status to Basic from Advanced for a Club she has RBAC rights to.",
            test_description=f"""Debbie tries to change RBAC status for {club_names[TRUMPS_ID]}
                                 from Advanced to Basic. As she is the club admin she will have been added to the
                                 RBAC groups now and this should work.""",
            reverse_result=False,
        )
