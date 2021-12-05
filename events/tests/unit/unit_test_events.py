from datetime import timedelta
from decimal import Decimal

from django.utils.timezone import localdate, localtime

from accounts.models import User
from events.models import CongressMaster, Congress, Event, Session, EventPlayerDiscount
from organisations.models import Organisation
from tests.test_manager import CobaltTestManagerIntegration

ENTRY_FEE = 100.0
EARLY_DISCOUNT = 20


class EventsTests:
    """Unit tests for things related to Events"""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager

    def events_model_functions(self):
        """Tests for functions that are part of the Event model"""

        # Create a congress
        org = Organisation.objects.get(pk=6)
        congress_master = CongressMaster(org=org, name="Model Test Congress Master")
        congress_master.save()
        congress = Congress(congress_master=congress_master)
        congress.save()

        self.manager.save_results(
            status=bool(congress),
            test_name="Create congress",
            test_description="Create a congress and check it works",
        )

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
        )

        # Create session
        session = Session(event=event)

        ####################################
        # Date checks                      #
        ####################################

        # With no dates, event should be open - pass
        assert event.is_open()

        today = localdate()
        # time_now = localtime().time()

        # Set Open date to yesterday - pass
        event.entry_open_date = today - timedelta(days=1)
        assert event.is_open()

        # Set Open date to tomorrow - fail
        event.entry_open_date = today + timedelta(days=1)
        assert not event.is_open()

        # Set open date to yesterday so we we can test the close date
        event.entry_open_date = today - timedelta(days=1)

        # Add close date set to tomorrow - pass
        event.entry_close_date = today + timedelta(days=1)
        assert event.is_open()

        # Set close date to yesterday - fail
        event.entry_close_date = today - timedelta(days=1)
        assert not event.is_open()

        # Set close date to today and close time to future - pass
        event.entry_close_date = today
        event.entry_close_time = (localtime() + timedelta(hours=1)).time()
        assert event.is_open()

        # Set close date to today and close time to past - fail
        event.entry_close_time = (localtime() - timedelta(hours=1)).time()
        assert not event.is_open()

        # Set close date to today and close time to past (try 1 second) - fail
        event.entry_close_time = (localtime() - timedelta(seconds=1)).time()
        assert not event.is_open()

        # Open event again so we can test the start date
        event.entry_close_date = today + timedelta(days=1)

        # Set start date in future - pass
        session.session_date = today + timedelta(days=7)
        session.session_start = (localtime() - timedelta(hours=1)).time()
        session.save()
        assert event.is_open()

        # Set start date in past - fail
        session.session_date = today - timedelta(days=7)
        session.save()
        assert not event.is_open()

        ##################
        # Entry Fees     #
        ##################

        # No discount
        player = User(
            first_name="Ready",
            last_name="PlayerOne",
            system_number=98989898,
            email="a@b.com",
        )
        player.save()
        fee, *_ = event.entry_fee_for(player)
        assert fee == ENTRY_FEE / 2

        # Early entry discount
        congress.allow_early_payment_discount = True
        congress.early_payment_discount_date = today + timedelta(days=1)
        congress.save()
        fee, _, desc, *_ = event.entry_fee_for(player)
        assert fee == (ENTRY_FEE - EARLY_DISCOUNT) / 2
        assert desc == "Early discount"

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
        assert fee == ((ENTRY_FEE - EARLY_DISCOUNT) / 2) * (50 / 100)
        assert desc == "Youth+Early discount"

        # Remove Early discount
        congress.allow_early_payment_discount = False
        congress.save()

        fee, _, desc, *_ = event.entry_fee_for(player)
        assert fee == (ENTRY_FEE / 2) * (50 / 100)
        assert desc == "Youth discount"

        # Specific player discounts
        event_player_discount = EventPlayerDiscount(
            player=player, admin=player, event=event, entry_fee=4.55, reason="ABC"
        )
        event_player_discount.save()

        fee, _, desc, *_ = event.entry_fee_for(player)
        assert fee == 4.55
        assert desc == "ABC"
