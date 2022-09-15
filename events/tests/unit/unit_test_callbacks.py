import random
import string

from accounts.models import User
from events.events_views.core import events_payments_primary_callback
from events.models import (
    Congress,
    Event,
    EventEntry,
    EventEntryPlayer,
    PlayerBatchId,
    BasketItem,
)
from notifications.tests.common_functions import check_email_sent
from payments.payments_views.core import update_account
from tests.test_manager import CobaltTestManagerIntegration
from post_office.models import Email


def _event_entry_test_helper(manager, test_name, event, entrants, expected_status):
    """Helper function for event entry

    Args:
        manager: CobaltTestManagerIntegration
        test_name(str): name of this test
        event(Event): event to enter
        entrants(list of lists [User, payment_type, expected_payment_state, email_body_search])
        expected_status(str): expected state of this entry after processing

    """

    # Generate random payload
    route_payload = "".join(random.choice(string.ascii_letters) for _ in range(10))

    primary_entrant = entrants[0][0]

    # Create event entry
    event_entry = EventEntry(event=event, primary_entrant=primary_entrant)
    event_entry.save()

    # Enter players
    team_entries = []
    for entrant in entrants:
        entry_fee, _, desc, *_ = event.entry_fee_for(entrant[0])
        # Is this part of this payment? only if my-system-dollars
        if entrant[1] == "my-system-dollars":
            this_route_payload = route_payload
        else:
            this_route_payload = None
        event_entry_player = EventEntryPlayer(
            event_entry=event_entry,
            player=entrant[0],
            payment_type=entrant[1],
            batch_id=this_route_payload,
            entry_fee=entry_fee,
            reason=desc,
        )
        event_entry_player.save()
        team_entries.append(event_entry_player)

    # Create other things we need
    PlayerBatchId(batch_id=route_payload, player=primary_entrant).save()
    BasketItem(player=primary_entrant, event_entry=event_entry).save()

    # Call the callback
    events_payments_primary_callback("Success", route_payload)

    # reload
    event_entry = EventEntry.objects.get(pk=event_entry.id)

    manager.save_results(
        status=event_entry.entry_status == expected_status,
        test_name=test_name,
        test_description=f"Create an entry, call the callback to confirm payment. Entrants are {entrants}",
        output=f"Checked for event_entry to be {expected_status}, got: {event_entry.entry_status}",
    )

    # Check individual status of player entries and emails
    for entrant in entrants:
        event_entry_player = EventEntryPlayer.objects.filter(
            event_entry=event_entry, player=entrant[0]
        ).first()
        manager.save_results(
            status=event_entry_player.payment_status == entrant[2],
            test_name=f"{test_name} - {entrant[0].first_name} - check entry",
            test_description=f"Check payment status for {entrant[0].first_name} after processing payment.",
            output=f"Checked payment status for {entrant[0].first_name}. Expected {entrant[2]}, got: {event_entry_player.payment_status}",
        )

        # If we got a search string, use that in the body
        body_search = entrant[3] if len(entrant) > 3 else None

        check_email_sent(
            manager=manager,
            test_name=f"{test_name} - {entrant[0].first_name} - check player email",
            test_description=f"Check the email for {entrant[0].first_name} was sent",
            subject_search="Event Entry",
            body_search=body_search,
            email_to=entrant[0].first_name,
        )

    # Check convener emails
    for convener in ["Colin", "Eric", "Fiona", "Gary", "Mark"]:
        check_email_sent(
            manager=manager,
            test_name=f"{test_name} - check convener email - {convener}",
            test_description="Check the email for the convener was sent",
            subject_search="New Entry to ",
            email_to=convener,
            debug=True,
        )


class CallbackTests:
    """Unit tests for the callbacks which are called when payments are made"""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager
        self.congress = Congress.objects.get(pk=1)
        self.pairs_event = Event.objects.get(pk=1)
        self.teams_event = Event.objects.get(pk=2)

    def primary_functions_pairs(self):
        """Tests for the callback for the primary entrant - pairs"""

        lucy = self.manager.lucy
        morris = self.manager.morris
        # natalie = self.manager.natalie
        # penelope = self.manager.penelope

        # Pairs - both my-system-dollars
        _event_entry_test_helper(
            manager=self.manager,
            test_name="Pairs entry - Both My Bridge Credits",
            event=self.pairs_event,
            entrants=[
                [lucy, "my-system-dollars", "Paid"],
                [morris, "my-system-dollars", "Paid"],
            ],
            expected_status="Complete",
        )

        # Pairs - my-system-dollars and ask them
        _event_entry_test_helper(
            manager=self.manager,
            test_name="Pairs entry My Bridge Credits and ask them",
            event=self.pairs_event,
            entrants=[
                [lucy, "my-system-dollars", "Paid"],
                [morris, "unknown", "Unpaid"],
            ],
            expected_status="Pending",
        )

        # Pairs - other-pp and bank-transfer
        _event_entry_test_helper(
            manager=self.manager,
            test_name="Pairs entry Club PP and Bank Transfer",
            event=self.pairs_event,
            entrants=[
                [
                    lucy,
                    "off-system-pp",
                    "Unpaid",
                    "We are expecting some payments for this entry from another pre-paid system",
                ],
                [
                    morris,
                    "bank-transfer",
                    "Unpaid",
                    "We are expecting some payments for this entry by bank transfer.",
                ],
            ],
            expected_status="Pending",
        )

        # TODO: Check why this fails

        # # Pairs - My Bridge Credits and Their Bridge Credits Insufficient funds
        # _event_entry_test_helper(
        #     manager=self.manager,
        #     test_name="Pairs entry My Bridge Credits and Their Bridge Credits. Insufficient funds",
        #     event=self.pairs_event,
        #     entrants=[
        #         [lucy, "my-system-dollars", "Paid"],
        #         [morris, "their-system-dollars", "Unpaid"],
        #     ],
        #     expected_status="Pending",
        # )

        # Give poor Morris some cash and try again
        update_account(
            member=morris,
            amount=1000.0,
            description="Cash",
            payment_type="Refund",
        )

        # Pairs - My Bridge Credits and Their Bridge Credits
        _event_entry_test_helper(
            manager=self.manager,
            test_name="Pairs entry My Bridge Credits and Their Bridge Credits. Sufficient funds",
            event=self.pairs_event,
            entrants=[
                [lucy, "my-system-dollars", "Paid"],
                [morris, "their-system-dollars", "Paid"],
            ],
            expected_status="Complete",
        )

    def primary_functions_teams(self):
        """Tests for the callback for the primary entrant - teams"""

        lucy = self.manager.lucy
        morris = self.manager.morris
        natalie = self.manager.natalie
        penelope = self.manager.penelope
        # betty = self.manager.betty

        # Teams - all my-system-dollars
        _event_entry_test_helper(
            manager=self.manager,
            test_name="Teams entry - All My Bridge Credits",
            event=self.pairs_event,
            entrants=[
                [lucy, "my-system-dollars", "Paid"],
                [morris, "my-system-dollars", "Paid"],
                [natalie, "my-system-dollars", "Paid"],
                [penelope, "my-system-dollars", "Paid"],
            ],
            expected_status="Complete",
        )

        # TODO: Teams of 5 have the status set before they are saved. The 5th player defaults to Unpaid, but should be Free
        # Teams - 5 players my-system-dollars
        # _event_entry_test_helper(
        #     manager=self.manager,
        #     test_name="Teams entry - Five players",
        #     event=self.pairs_event,
        #     entrants=[
        #         [lucy, "my-system-dollars", "Paid"],
        #         [morris, "my-system-dollars", "Paid"],
        #         [natalie, "my-system-dollars", "Paid"],
        #         [penelope, "my-system-dollars", "Paid"],
        #         # [betty, "free", "Gree"],
        #         [betty, "free", "Unpaid"],
        #     ],
        #     expected_status="Complete",
        # )
