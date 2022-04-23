from organisations.decorators import check_club_menu_access
from organisations.models import Organisation
from organisations.views.admin import (
    add_club_defaults,
    admin_club_rbac_convert_basic_to_advanced_sub,
)
from rbac.core import (
    rbac_get_group_by_name,
    rbac_add_user_to_group,
    rbac_get_admin_group_by_name,
    rbac_add_user_to_admin_group,
)
from tests.test_manager import CobaltTestManagerIntegration
from tests.unit.general_test_functions import get_django_client_object


def _test_club_menu_access(
    manager, club, user, test_name, test_type=None, expected_to_work=True
):
    """Helper function to see if a user can access a menu item

    We have a few decorators set up, the test_type controls which one we try to call

    """

    # Create a client for this user
    client = get_django_client_object(user)

    # Build a post and get the request object as it would be passed in by Django
    response = client.post("/", {"club_id": club.id})
    request = response.wsgi_request

    # The test decorator will return True if we get in or an HTTPResponse if the decorator diverts us to an error page
    if test_type == "members":
        return_check = isinstance(_test_decorator_members(request), bool)
    elif test_type == "comms":
        return_check = isinstance(_test_decorator_comms(request), bool)
    else:
        return_check = isinstance(_test_decorator_basic(request), bool)

    if return_check:
        # Call was successful
        worked = True
        success = bool(expected_to_work)
    else:
        # Call returned access denied page
        worked = False
        success = not expected_to_work
    manager.save_results(
        status=success,
        test_name=test_name,
        test_description=f"Check if {user.first_name} can access {club}.",
        output=f"Expected outcome was {expected_to_work}. Actual outcome was {worked}.",
    )


def _add_basic_access(user, club):
    """Give a user admin access to a club with basic RBAC"""

    # Get group
    group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.basic")

    # Add user to group
    rbac_add_user_to_group(user, group)

    # All users are admins
    admin_group = rbac_get_admin_group_by_name(
        f"{club.rbac_admin_name_qualifier}.admin"
    )
    rbac_add_user_to_admin_group(user, admin_group)


@check_club_menu_access()
def _test_decorator_basic(request, club):
    """Fake function to test the decorator"""

    return True


@check_club_menu_access(check_members=True)
def _test_decorator_members(request, club):
    """Fake function to test the decorator"""

    return True


@check_club_menu_access(check_comms=True)
def _test_decorator_comms(request, club):
    """Fake function to test the decorator"""

    return True


class ClubMenuDecoratorTests:
    """Unit tests for the decorator that controls access to menu items on the Club Menu"""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager
        self.alan = self.manager.alan
        self.betty = self.manager.betty
        self.colin = self.manager.colin

        # Create a club with basic RBAC - we change it later
        self.club = Organisation(name="Unit Test Club", secretary=self.manager.alan)
        self.club.type = "Club"
        self.club.state = "NSW"
        self.club.save()
        add_club_defaults(self.club)

    def test_01_basic_rbac_access(self):
        """Tests for basic RBAC access"""

        # add a user
        _add_basic_access(self.betty, self.club)

        # Betty should have all access, Colin should have none
        _test_club_menu_access(
            self.manager,
            self.club,
            self.betty,
            "Basic RBAC - Betty does have general access",
            "basic",
            expected_to_work=True,
        )
        _test_club_menu_access(
            self.manager,
            self.club,
            self.colin,
            "Basic RBAC - Colin doesn't have general access",
            "basic",
            expected_to_work=False,
        )
        _test_club_menu_access(
            self.manager,
            self.club,
            self.betty,
            "Basic RBAC - Betty does have member access",
            "members",
            expected_to_work=True,
        )
        _test_club_menu_access(
            self.manager,
            self.club,
            self.colin,
            "Basic RBAC - Colin doesn't have member access",
            "members",
            expected_to_work=False,
        )
        _test_club_menu_access(
            self.manager,
            self.club,
            self.betty,
            "Basic RBAC - Betty does have comms access",
            "comms",
            expected_to_work=True,
        )
        _test_club_menu_access(
            self.manager,
            self.club,
            self.colin,
            "Basic RBAC - Colin doesn't have comms access",
            "comms",
            expected_to_work=False,
        )

    def test_02_advanced_rbac_access(self):
        """Tests for advanced RBAC access"""

        # Change to advanced RBAC
        admin_club_rbac_convert_basic_to_advanced_sub(self.club)

        # Betty should have all access, Colin should have none
        _test_club_menu_access(
            self.manager,
            self.club,
            self.betty,
            "Advanced RBAC - Betty does have general access",
            "basic",
            expected_to_work=True,
        )
        _test_club_menu_access(
            self.manager,
            self.club,
            self.colin,
            "Advanced RBAC - Colin doesn't have general access",
            "basic",
            expected_to_work=False,
        )
        _test_club_menu_access(
            self.manager,
            self.club,
            self.betty,
            "Advanced RBAC - Betty does have member access",
            "members",
            expected_to_work=True,
        )
        _test_club_menu_access(
            self.manager,
            self.club,
            self.colin,
            "Advanced RBAC - Colin doesn't have member access",
            "members",
            expected_to_work=False,
        )
        _test_club_menu_access(
            self.manager,
            self.club,
            self.betty,
            "Advanced RBAC - Betty does have comms access",
            "comms",
            expected_to_work=True,
        )
        _test_club_menu_access(
            self.manager,
            self.club,
            self.colin,
            "Advanced RBAC - Colin doesn't have comms access",
            "comms",
            expected_to_work=False,
        )
