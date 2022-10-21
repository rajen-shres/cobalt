from time import sleep

from post_office.models import Email
from selenium.webdriver.support.select import Select

from events.models import EventEntryPlayer
from notifications.tests.common_functions import check_email_sent
from payments.views.core import get_balance
from payments.tests.integration.common_functions import stripe_manual_payment_screen


def _check_balances_are_correct(
    test_instance,
    player_list,
    player_balances_before,
    event,
    test_name,
    test_description,
):
    """compare balance before, balance after and entry fee"""

    # We expect these to change but not other types
    change_expected_payment_types = ["my-system-dollars", "their-system-dollars"]

    for player in player_list:
        balance_before = player_balances_before[player[0]]
        balance_after = get_balance(player[0])

        # Check if we expect the balance to change
        if len(player) >= 4 and player[4]:
            change_expected = True
        else:
            change_expected = False

        # What entry fee do we expect to be charged to users account. Not the real entry fee, just balance change
        if change_expected and player[1] not in change_expected_payment_types:
            entry_fee_paid = event.entry_fee_for(player[0])[0]
        else:
            entry_fee_paid = 0

        test_instance.manager.save_results(
            status=balance_after == balance_before - entry_fee_paid,
            output=f"User is {player[0]}. Balance before was: {balance_before}. Balance after is: {balance_after}. Balance change expected was : {entry_fee_paid}. This could be because the payment went through a manual stripe payment and the final balance was expected to be the same as the original balance.",
            test_name=f"{test_name}. Check balance - {player[0].first_name}",
            test_description=f"{test_description} - check balance for {player[0].first_name}",
        )


def enter_event(
    test_instance,
    entry_url,
    player_list,
    player0_payment_type=None,
):
    """Helper function for entering an event. Just fills in the screen and hits enter

    Args:
        test_instance(Klass): the calling class. We use some of its variables
        entry_url(str): URL of the entry page
        player_list(list of lists):
                                    player,
                                    payment type to select
                                    expected payment_status afterwards
                                    manual payment (balance won;t change)
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


def check_entry(
    test_instance,
    event,
    test_name,
    test_description,
    player_list,
):
    """Helper function for entering an event. Check the entries.

    Args:
        test_instance(Klass): the calling class. We use some of its variables
        event(Event): event to enter
        player_list(list of lists):
                                    player,
                                    payment type to select
                                    expected payment_status afterwards
                                    manual payment (balance won;t change)
    """

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
            debug=False,
        )

    # Delete event entry for next time, use last event_entry_player
    event_entry_player.event_entry.delete()

    # Delete emails too
    Email.objects.all().delete()


def enter_event_and_check(
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
        test_description(str)
        test_name(str)
        player_list(list of lists):
                                    player,
                                    payment type to select
                                    expected payment_status afterwards
                                    manual payment (balance won;t change)
        player0_payment_type (str): payment type for main entrant
    """

    # Get balances before we enter
    player_balances_before = {
        player[0]: get_balance(player[0]) for player in player_list
    }

    enter_event(test_instance, entry_url, player_list, player0_payment_type)

    # Wait for success screen
    test_instance.manager.selenium_wait_for_text(
        "Congresses", element_id="t_congress_heading"
    )

    # Check if it worked as expected
    check_entry(test_instance, event, test_name, test_description, player_list)

    # Check balances
    _check_balances_are_correct(
        test_instance,
        player_list,
        player_balances_before,
        event,
        test_name,
        test_description,
    )


def enter_event_then_pay_and_check(
    test_instance,
    event,
    entry_url,
    test_name,
    test_description,
    player_list,
    player0_payment_type=None,
):
    """Helper function for entering an event and paying with Stripe

    Args:
        test_instance(Klass): the calling class. We use some of its variables
        event(Event): event to enter
        entry_url(str): URL of the entry page
        test_description(str)
        test_name(str)
        player_list(list of lists):
                                    player,
                                    payment type to select
                                    expected payment_status afterwards
                                    manual payment (balance won;t change)
        player0_payment_type (str): payment type for main entrant
    """

    # enter event using selenium
    enter_event(test_instance, entry_url, player_list, player0_payment_type)

    # Wait for payment screen
    test_instance.manager.selenium_wait_for_text(
        "Credit Card Payment", element_id="id_credit_card_header"
    )

    # Make payment
    stripe_manual_payment_screen(test_instance.manager)

    # Check if it worked as expected
    sleep(5)
    check_entry(test_instance, event, test_name, test_description, player_list)
