"""

This should only be temporary.

If a basket item has an event which has received payments (by any player) then it shouldn't
be in the basket any more.

This was fixed in the code, but this script was needed to clean up older items.

"""

from django.core.management.base import BaseCommand

from events.models import EventEntry, BasketItem


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Cleaning up basket items that have paid entries")

        event_entries = EventEntry.objects.filter(
            evententryplayer__payment_status="Paid"
        ).values("id")

        basket_items = BasketItem.objects.filter(event_entry__in=event_entries)

        for basket_item in basket_items:
            print(
                f"player_id: {basket_item.player.id} event_entry_id: {basket_item.event_entry.id} player: {basket_item.player} event_entry: {basket_item.event_entry}"
            )
            basket_item.delete()
