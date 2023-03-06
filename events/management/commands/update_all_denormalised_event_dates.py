"""

This should only be temporary.

Denormalised dates were not originally in the database. New events get them added, this was
used to add them to historic events.

This version of the script actually does all events, as we had a problem with congresses being copied and the
dates not being updated.

"""

from django.core.management.base import BaseCommand

from events.models import EventEntry, BasketItem, Event
from events.views.congress_builder import update_event_start_and_end_times


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Updating all denormalised dates")

        all_events = Event.objects.all()

        for event in all_events:
            print(f"Replacing denormalised dates for {event}")
            update_event_start_and_end_times(event)
