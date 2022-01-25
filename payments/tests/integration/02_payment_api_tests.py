from payments.payments_views.core import update_account
from tests.test_manager import CobaltTestManagerIntegration


class PaymentAPITests:
    """Unit tests for payment api functions"""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager

    def payment_api_batch_tests(self):
        """Tests for payment_api_batch"""

        morris = self.manager.morris

        # Give Morris some money
        update_account(
            member=morris,
            amount=1000.0,
            description="Morris initial amount",
            log_msg=None,
            source=None,
            sub_source=None,
            payment_type="Refund",
        )

        # Make payment, sufficient funds
