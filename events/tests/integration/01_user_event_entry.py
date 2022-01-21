import time

from django.urls import reverse
from post_office import mail
from post_office.models import Email
from selenium.webdriver.support.select import Select

from accounts.models import TeamMate
from events.models import Event, Congress, EventEntryPlayer
from notifications.tests.common_functions import check_email_sent
from payments.payments_views.core import update_account
from tests.test_manager import CobaltTestManagerIntegration


def _enter_event_and_check(
    test_instance,
    event,
    entry_url,
    test_name,
    test_description,
    player_list,
    player0_payment_type=None,
):
    """Helper function for entering an event

    Args:
        test_instance(Klass): the calling class. We use some of its variables
        event(Event): event to enter
        entry_url(str): URL of the entry page
        player_list(list of lists):
                                    player,
                                    payment type to select
                                    expected payment_status afterwards
        player0_payment_type (str): payment type for main entrant
    """

    # Go to Entry page
    test_instance.manager.driver.get(entry_url)

    # set payment type for primary entrant if provided
    if player0_payment_type:
        test_instance.manager.selenium_wait_for_clickable("id_player0_payment")
        # select payment type field
        select_payment_type = Select(
            test_instance.manager.driver.find_element_by_id("id_player0_payment")
        )
        # select payment type value
        select_payment_type.select_by_value(player0_payment_type)

    for player_no, player in enumerate(player_list, start=1):
        # Wait
        test_instance.manager.selenium_wait_for_clickable(f"id_player{player_no}")
        # Select Player field
        select_player = Select(
            test_instance.manager.driver.find_element_by_id(f"id_player{player_no}")
        )
        # select Player value
        select_player.select_by_value(f"{player[0].id}")
        # Wait for JavaScript to catch up
        test_instance.manager.selenium_wait_for_clickable(
            f"id_player{player_no}_payment"
        )
        # select payment type field
        select_payment_type = Select(
            test_instance.manager.driver.find_element_by_id(
                f"id_player{player_no}_payment"
            )
        )
        # select payment type value
        select_payment_type.select_by_value(player[1])

    # Enter
    test_instance.manager.selenium_wait_for_clickable("id_checkout").click()

    # Wait for success screen
    test_instance.manager.selenium_wait_for_text(
        "Congresses", element_id="t_congress_heading"
    )

    # Check if it worked as expected

    for player in player_list:
        # Check event entry player
        event_entry_player = EventEntryPlayer.objects.filter(
            event_entry__event=event, player=player[0]
        ).first()

        test_instance.manager.save_results(
            status=event_entry_player.payment_status == player[2],
            output=f"Checked status of {player[0]} entry. Expected 'Paid', got '{event_entry_player.payment_status}'",
            test_name=f"{test_name}. Check event entry player - {player[0].first_name}",
            test_description=test_description,
        )

        # Check email
        check_email_sent(
            manager=test_instance.manager,
            test_name=f"{test_name} - {player[0].first_name} email",
            email_to=player[0].first_name,
            test_description=test_description,
            subject_search="Event Entry",
        )

    # Delete event entry for next time, use last event_entry_player
    event_entry_player.event_entry.delete()

    # Delete emails too
    Email.objects.all().delete()


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
        self.pairs_event = Event.objects.get(pk=1)
        self.teams_event = Event.objects.get(pk=2)

        self.pairs_entry_url = self.manager.base_url + reverse(
            "events:enter_event", kwargs={"congress_id": 1, "event_id": 1}
        )
        self.teams_entry_url = self.manager.base_url + reverse(
            "events:enter_event", kwargs={"congress_id": 1, "event_id": 2}
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

        # Both Bridge Credits
        _enter_event_and_check(
            test_name="Pairs entry for Keith - pays for both",
            test_description="Keith enters event and pays for Lucy",
            test_instance=self,
            event=self.pairs_event,
            entry_url=self.pairs_entry_url,
            player_list=[[self.manager.lucy, "my-system-dollars", "Paid"]],
        )

        # Bank Transfer
        _enter_event_and_check(
            test_name="Pairs entry for Keith - Bridge Credits and Bank Transfer",
            test_description="Keith enters event and sets Lucy to Bank Transfer",
            test_instance=self,
            event=self.pairs_event,
            entry_url=self.pairs_entry_url,
            player_list=[[self.manager.lucy, "bank-transfer", "Pending Manual"]],
        )

        # cash and bank transfer
        _enter_event_and_check(
            test_name="Pairs entry for Keith - Cash and Bank Transfer",
            test_description="Keith enters event with cash and sets Lucy to Bank Transfer",
            test_instance=self,
            event=self.pairs_event,
            entry_url=self.pairs_entry_url,
            player_list=[[self.manager.lucy, "bank-transfer", "Pending Manual"]],
            player0_payment_type="cash",
        )

    def a2_teams_entry(self):
        """Simple teams entry scenarios"""

        # All Bridge Credits
        _enter_event_and_check(
            test_name="Teams entry for Keith - pays for all",
            test_description="Keith enters event and pays for everyone",
            test_instance=self,
            event=self.teams_event,
            entry_url=self.teams_entry_url,
            player_list=[
                [self.manager.lucy, "my-system-dollars", "Paid"],
                [self.manager.morris, "my-system-dollars", "Paid"],
                [self.manager.natalie, "my-system-dollars", "Paid"],
            ],
        )
