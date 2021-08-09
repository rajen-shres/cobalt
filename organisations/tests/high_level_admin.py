from django.urls import reverse

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

        # Alan add a club

        # We have to use real clubs as it links to the MPC at the moment

        view_data = {
            "secretary": self.betty.id,
            "name": "North Shore Bridge Club Inc",
            "org_id": 2120,
            "club_email": "a@b.com",
            "club_website": "www.com",
            "address1": "20 Street Avenue",
            "suburb": "Wombleville",
            "state": "NSW",
            "postcode": 2000,
        }

        url = reverse("organisations:admin_add_club")
        response = self.client.post(url, view_data)
        print(response)
        print(response.context["form"])

        self.manager.save_results(
            status=response.status_code,
            test_name="Alan adds North Shore Bridge Club",
            test_description="Alan adds North Shore Bridge Club as a club. Alan has global admin so this should work. We have to use real club names as this connects to the MPC",
        )

        ###################################################

        # Betty add a club

        view_data["org_id"] = 2259
        view_data["name"] = "Trumps Bridge Centre"

        self.manager.login_test_client(self.betty)

        response = self.client.post(url, view_data)
        print(response.context["form"])

        self.manager.save_results(
            status=response.status_code,
            test_name="Betty adds Trumps",
            test_description="Betty adds Trumps as a club. Betty has NSW admin so this should work.",
        )


####################################################
