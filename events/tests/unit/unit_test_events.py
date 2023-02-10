from datetime import timedelta, time
from decimal import Decimal

from django.utils.timezone import localdate, localtime

from accounts.models import User
from events.models import (
    CongressMaster,
    Congress,
    Event,
    Session,
    EventPlayerDiscount,
    EventEntry,
    EventEntryPlayer,
)
from events.views.congress_builder import update_event_start_and_end_times
from events.views.core import get_events
from organisations.models import Organisation
from rbac.tests.utils import unit_test_rbac_add_role_to_user
from tests.test_manager import CobaltTestManagerIntegration
from tests.unit.general_test_functions import test_model_instance_is_safe

ENTRY_FEE = 100.0
EARLY_DISCOUNT = 20
TEST_ORG = 6


def _create_congress():
    org = Organisation.objects.get(pk=TEST_ORG)
    congress_master = CongressMaster(org=org, name="Model Test Congress Master")
    congress_master.save()
    congress = Congress(congress_master=congress_master)
    congress.save()
    return congress


def _create_player():
    player = User(
        first_name="Ready",
        last_name="PlayerOne",
        system_number=98989898,
        email="a@b.com",
    )
    player.save()
    return player


def _report_denormalised_dates(
    manager,
    event,
    expected_start_date,
    expected_end_date,
    expected_start_time,
    test_name,
):
    """helper to check dates"""
    if (
        event.denormalised_start_date == expected_start_date
        and event.denormalised_start_time == expected_start_time
        and event.denormalised_end_date == expected_end_date
    ):
        ok = True
    else:
        ok = False

    output = f"""Event start date is {event.denormalised_start_date}. Expected: {expected_start_date}
                Event start time is {event.denormalised_start_time}. Expected: {expected_start_time}
                Event end date is {event.denormalised_end_date}. Expected: {expected_end_date}
    """

    manager.save_results(
        status=ok,
        test_name=test_name,
        test_description="Starting with an empty event that has 3 sessions, add the denormalised dates and check them",
        output=output,
    )


def _dashboard_helper(
    manager,
    user,
    expected_unpaid,
    expected_more_events,
    expected_total_events,
    test_name,
    test_description,
):
    """helper for the events_dashboard tests"""

    event_entry_players, unpaid, more_events, total_events = get_events(user)

    ok = (
        expected_total_events == total_events
        and expected_more_events == more_events
        and expected_unpaid == unpaid
    )

    manager.save_results(
        status=ok,
        test_name=test_name,
        test_description=test_description,
        output=f"Expected unpaid: {expected_unpaid}. Unpaid: {unpaid} "
        f"Expected More: {expected_more_events}. More: {more_events} "
        f"Expected total: {expected_total_events}. Total: {total_events}",
    )

    return event_entry_players


class CongressModelTests:
    """Unit tests for things related to the Congress model"""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager

    def congress_model_functions(self):
        """Tests for functions that are part of the Congress model"""

        # create congress
        congress = _create_congress()

        self.manager.save_results(
            status=bool(congress),
            test_name="Create congress",
            test_description="Create a congress and check it works",
            output=f"Created a congress. Status={bool(congress)}",
        )

        # Check bleach is working on all fields
        test_model_instance_is_safe(self.manager, congress, ["additional_info"])

        # Test user_is_convener
        player = _create_player()

        is_convener = congress.user_is_convener(player)

        self.manager.save_results(
            status=not is_convener,
            test_name="User not a convener",
            test_description="Check that a normal user is not a convener for this congress",
            output=f"Checked normal user for convener status. Status={is_convener}",
        )

        # Now add them as a convener
        unit_test_rbac_add_role_to_user(player, "events", "org", "edit", TEST_ORG)

        is_convener = congress.user_is_convener(player)

        self.manager.save_results(
            status=is_convener,
            test_name="User is a convener",
            test_description="Add user as convener and check that they get convener status for this congress",
            output=f"Checked convener user for convener status. Status={is_convener}",
        )


class EventModelTests:
    """Unit tests for things related to the Event model"""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager

    def events_model_functions(self):
        """Tests for functions that are part of the Event model"""

        # Create a congress
        congress = _create_congress()

        # Create basic event
        event = Event(
            congress=congress,
            event_name="pytest event",
            event_type="Open",
            entry_fee=Decimal(ENTRY_FEE),
            entry_early_payment_discount=Decimal(EARLY_DISCOUNT),
            player_format="Pairs",
        )
        event.save()

        self.manager.save_results(
            status=bool(event),
            test_name="Create event",
            test_description="Create an event and check it works",
            output=f"Created an event. Status={bool(congress)}",
        )

        # Create session
        session = Session(event=event)

        self.manager.save_results(
            status=bool(session),
            test_name="Create session",
            test_description="Create a session within the event and check it works",
            output=f"Created a session. Status={bool(congress)}",
        )

        ####################################
        # Date checks                      #
        ####################################

        # With no dates, event should be open - pass
        self.manager.save_results(
            status=bool(event.is_open()),
            test_name="Event is open. No dates set.",
            test_description="Check that the event is open. We have not set any dates so it should be open by default.",
            output=f"Checked event open. Status={bool(event.is_open())}",
        )

        today = localdate()
        # time_now = localtime().time()

        # Set Open date to yesterday - pass
        event.entry_open_date = today - timedelta(days=1)

        self.manager.save_results(
            status=bool(event.is_open()),
            test_name="Event is open. Open date in past.",
            test_description="Add an open date in the past. Check that the event is open.",
            output=f"Checked event open. Status={bool(event.is_open())}. Today: {today}. Open date: {event.entry_open_date}",
        )

        # Set Open date to tomorrow - fail
        event.entry_open_date = today + timedelta(days=1)

        self.manager.save_results(
            status=not bool(event.is_open()),
            test_name="Event is not open. Open date in future.",
            test_description="Add an open date in the future. Check that the event is closed.",
            output=f"Checked event open. Status={bool(event.is_open())}. Today: {today}. Open date: {event.entry_open_date}",
        )

        # Set open date to yesterday so we we can test the close date
        event.entry_open_date = today - timedelta(days=1)

        # Add close date set to tomorrow - pass
        event.entry_close_date = today + timedelta(days=1)

        self.manager.save_results(
            status=bool(event.is_open()),
            test_name="Event is open. Open date in past. Close date in future.",
            test_description="Add a close date in the future. Check that the event is open.",
            output=f"Checked event open. Status={bool(event.is_open())}. Today: {today}. "
            f"Open date: {event.entry_open_date}. Close date: {event.entry_close_date}",
        )

        # Set close date to yesterday - fail
        event.entry_close_date = today - timedelta(days=1)

        self.manager.save_results(
            status=not bool(event.is_open()),
            test_name="Event is closed. Open date in past. Close date in past.",
            test_description="Add a close date in the past. Check that the event is closed.",
            output=f"Checked event open. Status={bool(event.is_open())}. Today: {today}. "
            f"Open date: {event.entry_open_date}. Close date: {event.entry_close_date}",
        )

        # Set close date to today and close time to future - pass
        event.entry_close_date = today
        event.entry_close_time = (localtime() + timedelta(hours=1)).time()

        self.manager.save_results(
            status=bool(event.is_open()),
            test_name="Event is open. Open date in past. Close date is today. Close time in future.",
            test_description="Add a close time in the future. Check that the event is open.",
            output=f"Checked event open. Status={bool(event.is_open())}. Today: {today}. "
            f"Open date: {event.entry_open_date}. Close date: {event.entry_close_date}. "
            f"Close date: {event.entry_close_time}",
        )

        # Set close date to today and close time to past - fail
        event.entry_close_time = (localtime() - timedelta(hours=1)).time()

        self.manager.save_results(
            status=not bool(event.is_open()),
            test_name="Event is closed. Open date in past. Close date is today. Close time in past.",
            test_description="Add a close time in the past. Check that the event is closed.",
            output=f"Checked event open. Status={bool(event.is_open())}. Today: {today}. Time: {localtime().time()} "
            f"Open date: {event.entry_open_date}. Close date: {event.entry_close_date}. "
            f"Close time: {event.entry_close_time}",
        )

        # Set close date to today and close time to past (try 1 second) - fail
        event.entry_close_time = (localtime() - timedelta(seconds=1)).time()
        self.manager.save_results(
            status=not bool(event.is_open()),
            test_name="Event is closed. Open date in past. Close date is today. Close time in past by 1 second.",
            test_description="Add a close time in the past (by 1 second). Check that the event is closed.",
            output=f"Checked event open. Status={bool(event.is_open())}. Today: {today}. Time: {localtime().time()} "
            f"Open date: {event.entry_open_date}. Close date: {event.entry_close_date}. "
            f"Close time: {event.entry_close_time}",
        )

        # Open event again so we can test the start date
        event.entry_close_date = today + timedelta(days=1)

        # Set start date in future - pass
        session.session_date = today + timedelta(days=7)
        session.session_start = (localtime() - timedelta(hours=1)).time()
        session.save()

        self.manager.save_results(
            status=bool(event.is_open()),
            test_name="Event is open. Open date in past. Close date is today. session date in future.",
            test_description="The event entry dates are fine (event is open) and the session date is in the future.",
            output=f"Checked event open. Status={bool(event.is_open())}. Today: {today}. Time: {localtime().time()} "
            f"Open date: {event.entry_open_date}. Close date: {event.entry_close_date}. "
            f"Close time: {event.entry_close_time}. Session date: {session.session_date}. "
            f"Session start: {session.session_start}",
        )

        # I don't think this is really correct - we don't use the session date for this calculation
        # so the test is invalid

        # # Set start date in past - fail
        # session.session_date = today - timedelta(days=7)
        # session.save()
        #
        # self.manager.save_results(
        #     status=not bool(event.is_open()),
        #     test_name="Event is closed. Open date in past. Close date is today. session date in past.",
        #     test_description="The event entry dates are fine (event is open) and the session date is in the past.",
        #     output=f"Checked event open. Status={bool(event.is_open())}. Today: {today}. Time: {localtime().time()} "
        #     f"Open date: {event.entry_open_date}. Close date: {event.entry_close_date}. "
        #     f"Close time: {event.entry_close_time}. Session date: {session.session_date}. "
        #     f"Session start: {session.session_start}",
        # )

        ##################
        # Entry Fees     #
        ##################

        # No discount
        player = _create_player()
        fee, *_ = event.entry_fee_for(player)

        ok = fee == ENTRY_FEE / 2

        self.manager.save_results(
            status=ok,
            test_name="Event entry fee. Pairs. No discounts.",
            test_description="Check the entry fee for a player in a pairs event with no discounts is "
            "half the total entry fee.",
            output=f"Checked event entry fee for {player}. Expected {ENTRY_FEE / 2}. Got {fee}.",
        )

        # Early entry discount
        congress.allow_early_payment_discount = True
        congress.early_payment_discount_date = today + timedelta(days=1)
        congress.save()
        fee, _, desc, *_ = event.entry_fee_for(player)

        if fee == (ENTRY_FEE - EARLY_DISCOUNT) / 2 and desc == "Early discount":
            ok = True
        else:
            ok = False

        self.manager.save_results(
            status=ok,
            test_name="Event entry fee. Pairs. Early entry discount.",
            test_description="Check the entry fee for a player in a pairs event with early entry discount is "
            "half the total entry fee after deducting the discount.",
            output=f"Checked event entry fee for {player}. Expected {(ENTRY_FEE - EARLY_DISCOUNT) / 2}. "
            f"Got {fee}. Expected description to be 'Early discount'. Got '{desc}'.",
        )

        # Youth Discount and early entry
        congress.allow_youth_payment_discount = True
        congress.youth_payment_discount_date = today
        congress.youth_payment_discount_age = 25
        congress.save()

        event.entry_youth_payment_discount = 50
        event.save()

        player.dob = today - timedelta(weeks=400)
        player.save()

        fee, _, desc, *_ = event.entry_fee_for(player)

        if (
            fee == ((ENTRY_FEE - EARLY_DISCOUNT) / 2) * (50 / 100)
            and desc == "Youth+Early discount"
        ):
            ok = True
        else:
            ok = False

        self.manager.save_results(
            status=ok,
            test_name="Event entry fee. Pairs. Early entry discount and youth discount.",
            test_description="Check the entry fee for a player in a pairs event with early entry discount and youth is "
            "half the total entry fee after deducting the discount then the youth discount taken off.",
            output=f"Checked event entry fee for {player}. Expected {((ENTRY_FEE - EARLY_DISCOUNT) / 2) * (50 / 100)}. "
            f"Got {fee}. Expected description to be 'Youth+Early discount'. Got '{desc}'.",
        )

        # Remove Early discount
        congress.allow_early_payment_discount = False
        congress.save()

        fee, _, desc, *_ = event.entry_fee_for(player)
        assert fee == (ENTRY_FEE / 2) * (50 / 100)
        assert desc == "Youth discount"

        if fee == (ENTRY_FEE / 2) * (50 / 100) and desc == "Youth discount":
            ok = True
        else:
            ok = False

        self.manager.save_results(
            status=ok,
            test_name="Event entry fee. Pairs. Only youth discount.",
            test_description="Check the entry fee for a player in a pairs event with youth discount is "
            "half the total entry fee with the youth discount taken off.",
            output=f"Checked event entry fee for {player}. Expected {(ENTRY_FEE / 2) * (50 / 100)}. "
            f"Got {fee}. Expected description to be 'Youth discount'. Got '{desc}'.",
        )

        # Specific player discounts
        event_player_discount = EventPlayerDiscount(
            player=player, admin=player, event=event, entry_fee=4.55, reason="ABC"
        )
        event_player_discount.save()

        fee, _, desc, *_ = event.entry_fee_for(player)
        assert fee == 4.55
        assert desc == "ABC"

        if fee == 4.55 and desc == "ABC":
            ok = True
        else:
            ok = False

        self.manager.save_results(
            status=ok,
            test_name="Event entry fee. Specific player setting.",
            test_description="Check specific entry fee is picked up.",
            output=f"Checked event entry fee for {player}. Expected 4.55. "
            f"Got {fee}. Expected description to be 'ABC'. Got '{desc}'.",
        )

    def events_denormalised_dates_functions(self):
        """Tests for adding and updating denormalised dates"""

        today = localdate()

        # Create a congress
        congress = _create_congress()

        # Create basic event
        event = Event(
            congress=congress,
            event_name="pytest event",
            event_type="Open",
            entry_fee=Decimal(ENTRY_FEE),
            entry_early_payment_discount=Decimal(EARLY_DISCOUNT),
            player_format="Pairs",
        )
        event.save()

        ######################
        # denormalised dates #
        ######################

        expected_start_date = today + timedelta(days=7)
        expected_end_date = today + timedelta(days=8)
        expected_start_time = time(10, 00)

        # Sort out starting data
        session = Session(event=event)
        session.session_date = expected_start_date
        session.session_start = expected_start_time
        session.session_end = None
        session.save()

        session2 = Session(event=event)
        session2.session_date = expected_end_date
        session2.session_start = expected_start_time
        session2.session_end = None
        session2.save()

        session3 = Session(event=event)
        session3.session_date = expected_end_date
        session3.session_start = time(14, 00)
        session3.session_end = None
        session3.save()

        # update the dates
        update_event_start_and_end_times(event)

        # Check dates
        _report_denormalised_dates(
            self.manager,
            event,
            expected_start_date,
            expected_end_date,
            expected_start_time,
            test_name="Adding denormalised dates to event",
        )

        # Change a session and try again
        expected_start_date = expected_end_date
        expected_start_time = time(7, 00)

        session.session_date = expected_start_date
        session.session_start = expected_start_time
        session.save()

        # update the dates
        update_event_start_and_end_times(event)

        # Check dates
        _report_denormalised_dates(
            self.manager,
            event,
            expected_start_date,
            expected_end_date,
            expected_start_time,
            test_name="Updating denormalised dates on event",
        )

    def events_dashboard(self):
        """Tests for the view presented on the dashboard"""

        today = localdate()
        natalie = self.manager.natalie

        # Create a congress
        congress = _create_congress()

        # Create basic event
        event = Event(
            congress=congress,
            event_name="pytest event",
            event_type="Open",
            entry_fee=Decimal(ENTRY_FEE),
            entry_early_payment_discount=Decimal(EARLY_DISCOUNT),
            player_format="Pairs",
        )
        event.save()

        # Create a session
        session = Session(event=event)
        session.session_date = today + timedelta(days=7)
        session.session_start = time(10, 00)
        session.session_end = None
        session.save()

        # Enter event
        event_entry = EventEntry(event=event, primary_entrant=natalie)
        event_entry.save()

        # Add player
        event_entry_player = EventEntryPlayer(event_entry=event_entry, player=natalie)
        event_entry_player.save()

        event_entry_players = _dashboard_helper(
            user=natalie,
            manager=self.manager,
            expected_unpaid=True,
            expected_more_events=False,
            expected_total_events=1,
            test_name="Pending Entry",
            test_description="Check entry in future is found and status is correct. Entry unpaid.",
        )

        self.manager.save_results(
            status=event_entry_players[0] == event_entry_player,
            test_name="Pending Entry - Check event_entry_player",
            test_description="Check that we get the event_entry_player we expect",
        )

        # Mark as paid
        event_entry_player.payment_status = "Paid"
        event_entry_player.save()

        event_entry_players = _dashboard_helper(
            user=natalie,
            manager=self.manager,
            expected_unpaid=False,
            expected_more_events=False,
            expected_total_events=1,
            test_name="Paid Entry",
            test_description="Check entry in future is found and status is correct. Entry is paid.",
        )

        self.manager.save_results(
            status=event_entry_players[0] == event_entry_player,
            test_name="Paid Entry - Check event_entry_player",
            test_description="Check that we get the event_entry_player we expect",
        )

        # In the past
        session.session_date = today - timedelta(days=1)
        session.save()
        update_event_start_and_end_times(event)

        event_entry_players = _dashboard_helper(
            user=natalie,
            manager=self.manager,
            expected_unpaid=False,
            expected_more_events=False,
            expected_total_events=0,
            test_name="No Upcoming",
            test_description="Check entry in past is not found.",
        )

        self.manager.save_results(
            status=len(event_entry_players) == 0,
            test_name="No Upcoming - Check event_entry_player",
            test_description="Check that we get empty event_entry_player as we expect",
        )

        # more than 5 entries
        # we cheat a bit and enter in the same event

        # fix session
        session.session_date = today + timedelta(days=7)
        session.save()
        update_event_start_and_end_times(event)

        # add entries
        entries_list = []
        for _ in range(6):
            event_entry_temp = EventEntry(event=event, primary_entrant=natalie)
            event_entry_temp.save()
            event_entry_player_temp = EventEntryPlayer(
                event_entry=event_entry_temp, player=natalie
            )
            event_entry_player_temp.save()
            entries_list.append(event_entry_player_temp)

        event_entry_players = _dashboard_helper(
            user=natalie,
            manager=self.manager,
            expected_unpaid=True,
            expected_more_events=True,
            expected_total_events=7,
            test_name="More than 5",
            test_description="Check more than 5 is handled.",
        )

        self.manager.save_results(
            status=len(event_entry_players) == 5,
            test_name="More than 5 - Check event_entry_player",
            test_description="Check that we get the event_entry_players we expect",
        )

        # Now the hard one - session dates

        # clean up, so we are back to just the one entry
        for event_entry_player_temp in entries_list:
            event_entry_player_temp.delete()

        # Set up sessions with gaps e.g. simulate weekly sessions
        # make first session in the past, last session in the future
        session.session_date = today - timedelta(days=10)
        session.save()

        session2 = Session(event=event)
        session2.session_date = today - timedelta(days=3)
        session2.session_start = time(10, 00)
        session2.save()

        session3 = Session(event=event)
        session3.session_date = today + timedelta(days=4)
        session3.session_start = time(10, 00)
        session3.save()

        event_entry_players = _dashboard_helper(
            user=natalie,
            manager=self.manager,
            expected_unpaid=False,
            expected_more_events=False,
            expected_total_events=1,
            test_name="Split sessions - midway",
            test_description="Sessions have gaps. Test we get the right session",
        )

        expected_start_date = today + timedelta(days=4)
        actual_start_date = event_entry_players[0].calculated_start_date
        expected_is_running = False
        try:
            actual_is_running = event_entry_players[0].is_running
        except AttributeError:
            actual_is_running = False

        self.manager.save_results(
            status=actual_start_date == expected_start_date,
            test_name="Split sessions - midway - Check event_entry_player",
            test_description="Check that we get the event_entry_players we expect",
            output=f"Expected start date: {expected_start_date}. Actual start date: {actual_start_date} "
            f"Expected is_running: {expected_is_running}. Actual is_running: {actual_is_running}",
        )

        # Now move date to be today

        session3.session_date = today
        session3.save()

        event_entry_players = _dashboard_helper(
            user=natalie,
            manager=self.manager,
            expected_unpaid=False,
            expected_more_events=False,
            expected_total_events=1,
            test_name="Split sessions - on day",
            test_description="Sessions have gaps. Test we get the right session. Today is a session day.",
        )

        expected_start_date = today
        actual_start_date = event_entry_players[0].calculated_start_date
        expected_is_running = True
        try:
            actual_is_running = event_entry_players[0].is_running
        except AttributeError:
            actual_is_running = False

        self.manager.save_results(
            status=actual_start_date == expected_start_date,
            test_name="Split sessions - on day - Check event_entry_player",
            test_description="Check that we get the event_entry_players we expect",
            output=f"Expected start date: {expected_start_date}. Actual start date: {actual_start_date} "
            f"Expected is_running: {expected_is_running}. Actual is_running: {actual_is_running}",
        )

        # Sessions on continuous days in future - expect first date returned

        session.session_date = today + timedelta(days=1)
        session.save()
        session2.session_date = today + timedelta(days=2)
        session2.save()
        session3.session_date = today + timedelta(days=3)
        session3.save()

        event_entry_players = _dashboard_helper(
            user=natalie,
            manager=self.manager,
            expected_unpaid=False,
            expected_more_events=False,
            expected_total_events=1,
            test_name="Continuous sessions - in future",
            test_description="Sessions have no gaps. Test we get the right session.",
        )

        expected_start_date = today + timedelta(days=1)
        actual_start_date = event_entry_players[0].calculated_start_date
        expected_is_running = False
        try:
            actual_is_running = event_entry_players[0].is_running
        except AttributeError:
            actual_is_running = False

        self.manager.save_results(
            status=actual_start_date == expected_start_date,
            test_name="Continuous sessions - in future - Check event_entry_player",
            test_description="Check that we get the event_entry_players we expect",
            output=f"Expected start date: {expected_start_date}. Actual start date: {actual_start_date} "
            f"Expected is_running: {expected_is_running}. Actual is_running: {actual_is_running}",
        )

        # continuous days - today is first day
        session.session_date = today
        session.save()
        session2.session_date = today + timedelta(days=1)
        session2.save()
        session3.session_date = today + timedelta(days=2)
        session3.save()

        event_entry_players = _dashboard_helper(
            user=natalie,
            manager=self.manager,
            expected_unpaid=False,
            expected_more_events=False,
            expected_total_events=1,
            test_name="Continuous sessions - today",
            test_description="Sessions have no gaps. Test we get the right session.",
        )

        expected_start_date = today
        actual_start_date = event_entry_players[0].calculated_start_date
        expected_is_running = True
        try:
            actual_is_running = event_entry_players[0].is_running
        except AttributeError:
            actual_is_running = False

        self.manager.save_results(
            status=actual_start_date == expected_start_date,
            test_name="Continuous sessions - today - Check event_entry_player",
            test_description="Check that we get the event_entry_players we expect",
            output=f"Expected start date: {expected_start_date}. Actual start date: {actual_start_date} "
            f"Expected is_running: {expected_is_running}. Actual is_running: {actual_is_running}",
        )

        # continuous days - today is second day
        session.session_date = today - timedelta(days=1)
        session.save()
        session2.session_date = today
        session2.save()
        session3.session_date = today + timedelta(days=1)
        session3.save()

        event_entry_players = _dashboard_helper(
            user=natalie,
            manager=self.manager,
            expected_unpaid=False,
            expected_more_events=False,
            expected_total_events=1,
            test_name="Continuous sessions - today day 2",
            test_description="Sessions have no gaps. Test we get the right session.",
        )

        expected_start_date = today
        actual_start_date = event_entry_players[0].calculated_start_date
        expected_is_running = True
        try:
            actual_is_running = event_entry_players[0].is_running
        except AttributeError:
            actual_is_running = False

        self.manager.save_results(
            status=actual_start_date == expected_start_date,
            test_name="Continuous sessions - today day 2 - Check event_entry_player",
            test_description="Check that we get the event_entry_players we expect",
            output=f"Expected start date: {expected_start_date}. Actual start date: {actual_start_date} "
            f"Expected is_running: {expected_is_running}. Actual is_running: {actual_is_running}",
        )
