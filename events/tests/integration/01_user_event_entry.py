import time

from django.urls import reverse
from selenium.webdriver.support.select import Select

from accounts.models import TeamMate
from events.models import Event, Congress
from notifications.tests.common_functions import check_email_sent
from payments.payments_views.core import update_account
from tests.test_manager import CobaltTestManagerIntegration


class EventEntry:
    """Tests for event entry through UI"""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager
        self.client = self.manager.client

        # Login Keith
        self.manager.login_user(self.manager.keith)

        # Set up Congress - My Big Congress
        self.congress = Congress.objects.get(pk=1)
        self.congress.payment_method_bank_transfer = True
        self.congress.payment_method_cash = True
        self.congress.payment_method_cheques = True
        self.congress.payment_method_off_system_pp = True
        self.congress.bank_transfer_details = "Gold bars"
        self.congress.cheque_details = "Pay to cash"
        self.congress.save()

        # Set up event - My Big Congress, Pairs
        self.event = Event.objects.get(pk=1)

        self.entry_url = self.manager.base_url + reverse(
            "events:enter_event", kwargs={"congress_id": 1, "event_id": 1}
        )

        # set up team mates for Keith
        TeamMate(
            user=self.manager.lucy, team_mate=self.manager.keith, make_payments=True
        ).save()
        TeamMate(
            user=self.manager.morris, team_mate=self.manager.keith, make_payments=True
        ).save()
        TeamMate(
            user=self.manager.natalie, team_mate=self.manager.keith, make_payments=True
        ).save()
        TeamMate(
            user=self.manager.penelope, team_mate=self.manager.keith, make_payments=True
        ).save()
        TeamMate(
            user=self.manager.keith, team_mate=self.manager.lucy, make_payments=True
        ).save()
        TeamMate(
            user=self.manager.keith, team_mate=self.manager.morris, make_payments=True
        ).save()
        TeamMate(
            user=self.manager.keith, team_mate=self.manager.natalie, make_payments=True
        ).save()
        TeamMate(
            user=self.manager.keith, team_mate=self.manager.penelope, make_payments=True
        ).save()

        # Give Keith some money
        update_account(
            member=self.manager.keith,
            amount=1000.0,
            description="Cash",
            log_msg=None,
            source=None,
            sub_source=None,
            payment_type="Refund",
        )

    def a1_pairs_entry(self):
        """Simple pairs entry scenarios"""

        # Keith enters with Lucy
        self.manager.driver.get(self.entry_url)

        # Select Lucy
        select = Select(self.manager.driver.find_element_by_id("id_player1"))
        select.select_by_value("17")

        # Wait for JS to catch up
        self.manager.selenium_wait_for_clickable("id_player1_payment")

        # Enter
        self.manager.selenium_wait_for_clickable("id_checkout").click()

        # Wait for success screen
        self.manager.selenium_wait_for_text(
            "Congresses", element_id="t_congress_heading"
        )

        # Check email
        check_email_sent(
            manager=self.manager,
            test_name="Keith enters pairs with Lucy and pays himself",
            test_description="Keith enters a pairs event with Lucy and used his bridge credits to pay",
            subject_search="Event Entry - Our Big Congress",
        )

        check_email_sent(
            manager=self.manager,
            test_name="Keith enters pairs with Lucy and pays himself",
            test_description="Keith enters a pairs event with Lucy and used his bridge credits to pay",
            subject_search="Event",
        )
