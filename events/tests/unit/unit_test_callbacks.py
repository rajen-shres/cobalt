import time

from accounts.models import User
from events.events_views.core import events_payments_callback
from events.models import (
    Congress,
    Event,
    EventEntry,
    EventEntryPlayer,
    PlayerBatchId,
    BasketItem,
)
from notifications.tests.common_functions import check_email_sent
from tests.test_manager import CobaltTestManagerIntegration


class CallbackTests:
    """Unit tests for the callbacks which are called when payments are made"""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager
        self.congress = Congress.objects.get(pk=1)
        self.event = Event.objects.get(pk=1)

    def primary_functions_pairs(self):
        """Tests for the callback for the primary entrant - pairs"""

        lucy = self.manager.lucy
        morris = self.manager.morris
        # natalie = self.manager.natalie
        # penelope = self.manager.penelope

        # Basic pairs entry with bridge credits - lucy + morris
        route_payload = "123456"
        event_entry = EventEntry(event=self.event, primary_entrant=lucy)
        event_entry.save()
        entry_fee, _, desc, *_ = self.event.entry_fee_for(lucy)
        lucy_entry = EventEntryPlayer(
            event_entry=event_entry,
            player=lucy,
            payment_type="their-system-dollars",
            batch_id=route_payload,
            entry_fee=entry_fee,
            reason=desc,
        )
        lucy_entry.save()
        morris_entry = EventEntryPlayer(
            event_entry=event_entry,
            player=morris,
            payment_type="their-system-dollars",
            batch_id=route_payload,
            entry_fee=entry_fee,
            reason=desc,
        )
        morris_entry.save()
        PlayerBatchId(batch_id=route_payload, player=lucy).save()
        BasketItem(player=lucy, event_entry=event_entry).save()

        # Call the callback
        events_payments_callback("Success", route_payload)

        # reload
        event_entry = EventEntry.objects.get(pk=event_entry.id)

        self.manager.save_results(
            status=event_entry.entry_status == "Complete",
            test_name="Pairs entry (Lucy, Morris) My Bridge Credits",
            test_description="Create an entry, call the callback to confirm payment. "
            "Check entries are paid",
            output=f"Checked for event_entry to be Complete, got: {event_entry.entry_status}",
        )

        # Check emails
        check_email_sent(
            manager=self.manager,
            test_name="Pairs entry (Lucy, Morris) My Bridge Credits. Lucy Email.",
            test_description="Check the email for Lucy was sent",
            subject_search="Event Entry - Our Big Congress",
            email_to="Lucy",
        )

        check_email_sent(
            manager=self.manager,
            test_name="Pairs entry (Lucy, Morris) My Bridge Credits. Morris Email.",
            test_description="Check the email for Morris was sent",
            subject_search="Event Entry - Our Big Congress",
            email_to="Morris",
        )

        # Check convener emails
        for convener in ["Colin", "Eric", "Fiona", "Gary", "Mark"]:
            check_email_sent(
                manager=self.manager,
                test_name=f"Pairs entry (Lucy, Morris) My Bridge Credits. Convener Email - {convener}.",
                test_description="Check the email for the convener was sent",
                subject_search="New Entry to Welcome Pairs in Our Big Congress",
                email_to=convener,
            )
