from datetime import timedelta
from decimal import Decimal

from django.utils.timezone import localdate, localtime

from events.models import CongressMaster, Congress, Event
from organisations.models import Organisation


def events_model_functions():

    # Create a congress
    org = Organisation.objects.get(pk=6)
    congress_master = CongressMaster(org=org, name="Model Test Congress Master")
    congress_master.save()
    congress = Congress(congress_master=congress_master)
    congress.save()

    assert congress

    # Create basic event
    event = Event(
        congress=congress,
        event_name="pytest event",
        event_type="Open",
        entry_fee=Decimal(100),
        entry_early_payment_discount=Decimal(20.0),
        player_format="Pairs",
    )
    event.save()

    assert event

    ####################################
    # Date checks                      #
    ####################################

    # With no dates, event should be open
    assert event.is_open()

    today = localdate()
    time_now = localtime().time()
    print(time_now)

    # Set Open date to yesterday
    event.entry_open_date = today - timedelta(days=1)
    assert event.is_open()

    # Set Open date to tomorrow
    event.entry_open_date = today + timedelta(days=1)
    print(event.entry_open_date)
    assert not event.is_open()
