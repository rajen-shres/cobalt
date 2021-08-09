"""
    Common functions for organisations.
"""
from django.urls import reverse

from accounts.models import User
from organisations.models import Organisation
from tests.test_manager import CobaltTestManager


def add_club(
    manager: CobaltTestManager, user: User = None, view_data=None, reverse_result=False
):
    """Common function to try to add a club

    Args:
        manager: test_manager.Manager object for interacting with system
        user: User object
        view_data: dic thing for the view
        reverse_result: swap True for False - we want this to fail
    """

    url = reverse("organisations:admin_add_club")

    # log user in
    manager.login_test_client(user)

    response = manager.client.post(url, view_data)

    ok = response.status_code == 302

    if reverse_result:
        ok = not ok
        desc = f"{user.first_name} adds {view_data['name']} as a club but doesn't have permission.  This should fail. We should get a redirect if it works."
        test_name = (
            f"{user.first_name} adds {view_data['name']}. Should fail - Redirect"
        )
        output = f"Checking we didn't redirected. {ok}"
    else:
        desc = f"{user.first_name} adds {view_data['name']} as a club.  We have to use real club names as this connects to the MPC. We should get a redirect if it works."
        test_name = f"{user.first_name} adds {view_data['name']} - Redirect"
        output = f"Checking we got redirected. {ok}"

    manager.save_results(
        status=ok, test_name=test_name, output=output, test_description=desc
    )

    ok = Organisation.objects.filter(org_id=view_data["org_id"]).exists()

    if reverse_result:
        ok = not ok
        test_name = f"{user.first_name} adds {view_data['name']}. Should fail - Check doesn't exist"
        desc = "Check that an org with this id doesn't exists. This test is expected to fail. Invalid permissions."
        output = f"Shouldn't find org with org_id={view_data['org_id']}. {ok}."
    else:
        test_name = f"{user.first_name} adds {view_data['name']} - Check exists"
        desc = "Check that an org with this id exists. Invalid test if it existed before we tried to add it."
        output = f"Should find org with org_id={view_data['org_id']}. {ok}."

    manager.save_results(
        status=ok,
        test_name=test_name,
        output=output,
        test_description=desc,
    )
