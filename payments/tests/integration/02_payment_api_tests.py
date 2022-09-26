from accounts.models import User
from organisations.models import Organisation
from payments.views.payments_api import (
    payment_api_batch,
    payment_api_interactive,
)
from payments.tests.integration.common_functions import (
    check_balance_for_user,
    check_balance_for_org,
    set_balance_for_member,
    set_balance_for_org,
)
from tests.test_manager import CobaltTestManagerIntegration
from tests.unit.general_test_functions import get_django_request_object


def _payment_api_test_function(
    manager: CobaltTestManagerIntegration,
    test_user: User,
    test_org: Organisation,
    test_name: str,
    test_description: str,
    test_type: str = "batch",
    expect_to_succeed: bool = True,
):
    """Helper for testing the payment api"""

    user_expected_initial_balance = 512.26
    org_expected_initial_balance = 34305.51

    # Set to pass or fail
    transfer_amount = (
        50.67 if expect_to_succeed else user_expected_initial_balance + 50.0
    )

    # Give user some money
    set_balance_for_member(test_user, user_expected_initial_balance)

    # Give org some money
    set_balance_for_org(test_org, org_expected_initial_balance)

    # Pre-checks
    _payment_batch_api_test_pre_checks(
        manager=manager,
        test_user=test_user,
        test_org=test_org,
        test_name=test_name,
        user_expected_initial_balance=user_expected_initial_balance,
        org_expected_initial_balance=org_expected_initial_balance,
    )

    # Make payment - depends on what type of payment we are doing - batch or interactive
    if test_type == "batch":
        return_code = payment_api_batch(
            member=test_user,
            amount=transfer_amount,
            description="Test 1",
            organisation=test_org,
        )

        manager.save_results(
            status=return_code == expect_to_succeed,
            test_name=f"{test_name} {test_user.first_name} pays {test_org}",
            test_description=test_description,
            output=f"Expected {expect_to_succeed}, got {return_code}",
        )

    elif test_type == "interactive":
        request = get_django_request_object(test_user)
        response = payment_api_interactive(
            request=request,
            member=test_user,
            amount=transfer_amount,
            description="Test 1",
            organisation=test_org,
            next_url="/success",
        )

        # If we succeed then we will get redirected to next_url,
        # if we fail we get a page returned (stripe manual payment page)
        if expect_to_succeed:
            if response.status_code == 302 and response.url == "/success":
                ok = True
            else:
                ok = False
        else:
            ok = response.status_code == 200

        manager.save_results(
            status=ok,
            test_name=f"{test_name} {test_user.first_name} pays {test_org}",
            test_description=f"{test_description} Successful payments give us a redirect to /success. "
            f"Unsuccessful payments return the stripe manual page.",
            output=f"Expected {expect_to_succeed}. Response was {response.status_code}. (302 is success, 200 is failure.)",
        )

    # If we set to fail then balances shouldn't change
    user_expected_final_balance = (
        user_expected_initial_balance - transfer_amount
        if expect_to_succeed
        else user_expected_initial_balance
    )
    org_expected_final_balance = (
        org_expected_initial_balance + transfer_amount
        if expect_to_succeed
        else org_expected_initial_balance
    )

    # Post checks
    _payment_batch_api_test_post_checks(
        manager=manager,
        test_user=test_user,
        test_org=test_org,
        test_name=test_name,
        user_expected_final_balance=user_expected_final_balance,
        org_expected_final_balance=org_expected_final_balance,
    )


def _payment_batch_api_test_pre_checks(
    manager: CobaltTestManagerIntegration,
    test_user: User,
    test_org: Organisation,
    user_expected_initial_balance: float,
    org_expected_initial_balance: float,
    test_name: str,
):
    """Helper for testing the payment batch api - do the pre-checks"""

    check_balance_for_user(
        manager=manager,
        user=test_user,
        expected_balance=user_expected_initial_balance,
        test_name=f"{test_name} Check initial balance for {test_user.first_name}",
        test_description=f"This is the initial check of {test_user.first_name}'s balance before we process the transfer.",
    )

    check_balance_for_org(
        manager=manager,
        org=test_org,
        expected_balance=org_expected_initial_balance,
        test_name=f"{test_name} Check initial balance for {test_org}",
        test_description=f"This is the initial check of {test_org}'s balance before we process the transfer.",
    )


def _payment_batch_api_test_post_checks(
    manager: CobaltTestManagerIntegration,
    test_user: User,
    test_org: Organisation,
    test_name: str,
    user_expected_final_balance: float,
    org_expected_final_balance: float,
):
    check_balance_for_user(
        manager=manager,
        user=test_user,
        expected_balance=user_expected_final_balance,
        test_name=f"{test_name} Check final balance for {test_user.first_name}",
        test_description=f"This is the final check of {test_user.first_name}'s balance after we process the transfer.",
    )

    check_balance_for_org(
        manager=manager,
        org=test_org,
        expected_balance=org_expected_final_balance,
        test_name=f"{test_name} Check final balance for {test_org}",
        test_description=f"This is the final check of {test_org}'s balance after we process the transfer.",
    )


class PaymentAPITests:
    """Unit tests for payment api functions. Assumes Alan has been set up for Auto top up by previous tests.

    We use a mixture of unit tests (payment_api_batch) and integration tests (payment_api_interactive)
    """

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager
        self.fantasy_bridge_club = Organisation.objects.filter(
            name="Fantasy Bridge Club"
        ).first()

    def payment_api_batch_tests(self):
        """Tests for payment_api_batch"""

        # Test pass
        _payment_api_test_function(
            self.manager,
            test_user=self.manager.alan,
            test_org=self.fantasy_bridge_club,
            test_name="Batch API call with sufficient funds.",
            test_description="We expect this payment to go through correctly",
            test_type="batch",
        )

        # Test fail
        _payment_api_test_function(
            self.manager,
            test_user=self.manager.alan,
            test_org=self.fantasy_bridge_club,
            test_name="Batch API call with insufficient funds.",
            test_description="We expect this payment to fail",
            test_type="batch",
            expect_to_succeed=False,
        )

    def payment_api_interactive_tests(self):
        """Tests for payment_api_batch"""

        # Test pass
        _payment_api_test_function(
            self.manager,
            test_user=self.manager.alan,
            test_org=self.fantasy_bridge_club,
            test_name="Interactive API call with sufficient funds.",
            test_description="We expect this payment to go through correctly without taking us to the stripe screen.",
            test_type="interactive",
        )

        # Test fail (go to manual screen, which we don't test here)
        _payment_api_test_function(
            self.manager,
            test_user=self.manager.alan,
            test_org=self.fantasy_bridge_club,
            test_name="Interactive API call with insufficient funds.",
            test_description="We expect this payment to go fail by taking us to the stripe manual screen.",
            test_type="interactive",
            expect_to_succeed=False,
        )
