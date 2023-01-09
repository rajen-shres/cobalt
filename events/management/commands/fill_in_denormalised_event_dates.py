"""

This should only be temporary.

Denormalised dates were not originally in the database. New events get them added, this was
used to add them to historic events.

"""

from django.core.management.base import BaseCommand

from events.models import EventEntry, BasketItem, Event
from events.views.congress_builder import update_event_start_and_end_times


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Adding denormalised dates")

        missing_dates = Event.objects.filter(denormalised_start_date=None)
        missing_dates_count = missing_dates.count()
        print(f"Events without denormalised_start_date: {missing_dates_count}")

        for missing_date in missing_dates:
            update_event_start_and_end_times(missing_date)

        missing_dates = Event.objects.filter(denormalised_start_date=None)
        missing_dates_count = missing_dates.count()
        print(
            f"Events without denormalised_start_date after processing: {missing_dates_count}"
        )

        for missing_date in missing_dates:
            print(missing_date.id, missing_date)
