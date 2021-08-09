from pprint import pprint

from django.urls import reverse

from organisations.models import Organisation
from organisations.tests.common_functions import add_club
from rbac.core import rbac_user_has_role
from tests.test_manager import CobaltTestManager

# State id numbers
NSW = 3
QLD = 5


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
        north_shore_id = 2120
        trumps_id = 2259
        sunshine_id = 4860
        waverley_id = 3480

        ns_ok = not Organisation.objects.filter(org_id=north_shore_id).exists()
        tr_ok = not Organisation.objects.filter(org_id=trumps_id).exists()
        su_ok = not Organisation.objects.filter(org_id=sunshine_id).exists()

        ok = ns_ok and tr_ok and su_ok

        self.manager.save_results(
            status=ok,
            test_name="Check orgs not present",
            output=f"Checking if orgs exists: {not ok}",
            test_description="Before we start we check that the organisations don't exist.",
        )

        #############################################################

        view_data = {
            "secretary": self.betty.id,
            "name": "North Shore Bridge Club Inc",
            "org_id": north_shore_id,
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
        view_data["org_id"] = trumps_id
        view_data["state"] = "NSW"
        view_data["name"] = "Trumps Bridge Centre"
        add_club(self.manager, self.betty, view_data)

        # Colin add a club - should work
        view_data["org_id"] = sunshine_id
        view_data["state"] = "QLD"
        view_data["name"] = "Sunshine Coast Contract Bridge Club Inc"
        add_club(self.manager, self.colin, view_data)

        # Betty add a club - should fail
        view_data["org_id"] = waverley_id
        view_data["state"] = "VIC"
        view_data["name"] = "Waverley Bridge Club"
        add_club(self.manager, self.betty, view_data, reverse)

        # Colin add a club - should fail
        add_club(self.manager, self.colin, view_data, reverse)
