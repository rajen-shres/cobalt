import logging
from datetime import datetime, timedelta, date

import pytz
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.template import loader
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

import payments.payments_views.core as payments_core  # circular dependency
from accounts.models import User
from cobalt.settings import (
    COBALT_HOSTNAME,
    BRIDGE_CREDITS,
    GLOBAL_ORG,
    TIME_ZONE,
    TBA_PLAYER,
)
from events.models import PAYMENT_TYPES
from logs.views import log_event
from notifications.models import BlockNotification
from notifications.notifications_views.core import send_cobalt_email_with_template
from payments.payments_views.payments_api import (
    payment_api_batch,
    calculate_auto_topup_amount,
)
from rbac.core import rbac_get_users_with_role
from events.models import (
    BasketItem,
    EventEntry,
    EventEntryPlayer,
    PlayerBatchId,
    EventLog,
    Congress,
)

TZ = pytz.timezone(TIME_ZONE)

logger = logging.getLogger("cobalt")


def events_payments_secondary_callback(status, route_payload):
    """This gets called when (potentially) multiple payments have been made for an event_entry_player by
    someone other than the primary entrant.

    This is called when a user hits Pay All on the edit screen or when they click to pay only one players entry

    The only difference is number of items in the list of entries with matching batch ids

    """

    payment_user = _get_player_who_is_paying(status, route_payload)

    if not payment_user:
        return

    # Get players and entries that have been paid for (could be ab empty list, but shouldn't be)
    paid_event_entry_players = _get_event_entry_players_from_payload(route_payload)

    if not paid_event_entry_players:
        return

    # Update entries
    for paid_event_entry_player in paid_event_entry_players:
        _mark_event_entry_player_as_paid_and_book_payments(
            paid_event_entry_player, payment_user
        )

    # Check if still in primary entrants basket and handle
    _events_payments_secondary_callback_process_basket(
        event_entry=paid_event_entry_players[0].event_entry,
        already_handled_event_entry_players=paid_event_entry_players,
        team_mate_who_triggered=payment_user,
    )


def _events_payments_secondary_callback_process_basket(
    event_entry, already_handled_event_entry_players, team_mate_who_triggered
):
    """Handle this event still being in the primary users basket when a team mate makes a payment"""

    # This entry could have been in the primary players basket
    basket_item = BasketItem.objects.filter(event_entry=event_entry).first()

    if not basket_item:
        return

    # Delete from primary entrants basket if it was still there
    basket_item.delete()

    # Get the primary entrant, we now need to look at things from their point of view as if they had
    # checked out the entry
    primary_entrant = event_entry.primary_entrant

    # We should try to make any payments for this entry that would have been made if the primary entrant had
    # checked out, but only if we can do it without manual payment. And also send the emails.
    # We probably shouldn't do any team mate allowed payments as this user may not have access

    # get all event_entry_players for this entry
    event_entry_all_players = EventEntryPlayer.objects.filter(event_entry=event_entry)

    for event_entry_all_player in event_entry_all_players:

        # Skip any that have already been handled
        if event_entry_all_player in already_handled_event_entry_players:
            continue

        # From the point of view of the primary entrant
        if (
            # primary entrant said they would pay
            event_entry_all_player.payment_type == "my-system-dollars"
            # entry isn't yet paid
            and event_entry_all_player.payment_status not in ["Paid", "Free"]
            # payment works
            and payment_api_batch(
                member=primary_entrant,
                description=event_entry.event.event_name,
                amount=event_entry_all_player.entry_fee
                - event_entry_all_player.payment_received,
                organisation=event_entry.event.congress.congress_master.org,
                payment_type="Entry to an event",
                book_internals=False,
            )
        ):
            _mark_event_entry_player_as_paid_and_book_payments(
                event_entry_all_player, primary_entrant
            )

    # Let people know
    _send_notifications(
        event_entry_players=event_entry_all_players,
        event_entries=event_entry_all_players,
        payment_user=primary_entrant,
        triggered_by_team_mate_payment=True,
        team_mate_who_triggered=team_mate_who_triggered,
    )


def events_payments_primary_callback(status, route_payload):
    """This gets called when a payment has been made for us.

    We supply the route_payload when we ask for the payment to be made and
    use it to update the status of payments.

    This gets called when the primary user who is entering the congress
    has made a payment.

    We can use the route_payload to find the payment_user (who entered and paid)
    as well as to find all of the EventEntryPlayer records that have been paid for if this was successful.

    We also need to notify everyone who has been entered which will include people who were not
    paid for by this payment. For that we use the basket of the primary user, which we then empty.

    This requires an EventEntry, a group of EventEntryPlayers with the route_payload attached,
    A PlayerBatchId to find the player who made this entry, and the BasketItems for that player.

    """

    payment_user = _get_player_who_is_paying(status, route_payload)

    if not payment_user:
        return

    # Get players and entries that have been paid for
    paid_event_entry_players = _get_event_entry_players_from_payload(route_payload)
    paid_event_entries = _get_event_entries_for_event_entry_players(
        paid_event_entry_players
    )

    # Update them
    _update_entries(paid_event_entry_players, paid_event_entries, payment_user)

    # Get all players that are included in this bunch of entries
    notify_event_entry_players = _get_event_entry_players_from_basket(payment_user)
    notify_event_entries = _get_event_entries_for_event_entry_players(
        notify_event_entry_players
    )

    # Notify them
    _send_notifications(notify_event_entry_players, notify_event_entries, payment_user)

    # Tidy up
    _clean_up(payment_user)


def _get_player_who_is_paying(status, route_payload):
    """Use the route_payload to find the player who is paying for this batch of entries
    Also checks the status (to avoid duplicate code) and deletes the PlayerBatchId object
    """

    if status != "Success":
        logger.warning(
            f"Received callback with status {status}. Payload {route_payload}. Ignoring."
        )
        return False

    # Find who is making this payment
    player_batch_id = PlayerBatchId.objects.filter(batch_id=route_payload).first()

    # catch error
    if not player_batch_id:
        log_event(
            user="Unknown",
            severity="CRITICAL",
            source="Events",
            sub_source="events_payments_callback",
            message=f"No matching player for route_payload: {route_payload}",
        )
        logger.critical(f"No matching player for route_payload: {route_payload}")
        return False

    payment_user = player_batch_id.player
    player_batch_id.delete()

    return payment_user


def _get_event_entry_players_from_payload(route_payload):
    """Returns the entries that are associated with the route_payload. Route_payload is sent as a parameter
    to Stripe so we when a payment is made we can find the corresponding entries.

    Note: These are the evententry_player records that were paid for, not the total entries.
          There could be other entries in this that were paid for using a different method."""

    return EventEntryPlayer.objects.filter(batch_id=route_payload)


def _get_event_entry_players_from_basket(payment_user):
    """Get all of the EventEntryPlayer records that need to be notified. Use the primary players basket."""

    return EventEntryPlayer.objects.filter(
        event_entry__basketitem__player=payment_user
    ).exclude(event_entry__entry_status="Cancelled")


def _get_event_entries_for_event_entry_players(event_entry_players):
    """Takes a list of event entry players and returns the parent event entries

    Args:
        event_entry_players: a query set of EventEntryPlayers

    Returns:
        event_entries: a query set of EventEntries
    """

    # Get all EventEntries for changed EventEntryPlayers
    event_entry_list = (
        event_entry_players.order_by("event_entry", "-id")
        .distinct("event_entry")
        .values_list("event_entry")
    )

    return EventEntry.objects.filter(pk__in=event_entry_list).exclude(
        entry_status="Cancelled"
    )


def _update_entries(event_entry_players, event_entries, payment_user):
    """Update the database to reflect changes and make payments for
    other members if we have access."""

    # Change the entries that have been paid for
    _update_entries_change_entries(event_entry_players, payment_user)

    # Check if we can now pay using "their system dollars"
    _update_entries_process_their_system_dollars(event_entries)

    # Update status
    for event_entry in event_entries:
        event_entry.check_if_paid()


def _update_entries_change_entries(event_entry_players, payment_user):
    """First part of _update_entries. This changes the entries themselves"""

    # Update EntryEventPlayer objects
    for event_entry_player in event_entry_players:
        _mark_event_entry_player_as_paid_and_book_payments(
            event_entry_player, payment_user
        )


def _mark_event_entry_player_as_paid_and_book_payments(event_entry_player, who_paid):
    """Update a single event_entry_player record to be paid, and create the payments for the
    user and the organisation"""

    # this could be a partial payment
    amount = event_entry_player.entry_fee - event_entry_player.payment_received

    event_entry_player.payment_status = "Paid"
    event_entry_player.payment_received = event_entry_player.entry_fee
    event_entry_player.paid_by = who_paid
    event_entry_player.entry_complete_date = timezone.now().astimezone(TZ)
    event_entry_player.save()

    EventLog(
        event=event_entry_player.event_entry.event,
        actor=event_entry_player.paid_by,
        action=f"Paid for {event_entry_player.player} with {amount} {BRIDGE_CREDITS}",
        event_entry=event_entry_player.event_entry,
    ).save()

    log_event(
        user=event_entry_player.paid_by.href,
        severity="INFO",
        source="Events",
        sub_source="events_entry",
        message=f"{event_entry_player.paid_by.href} paid for {event_entry_player.player.href} to enter {event_entry_player.event_entry.event.href}",
    )

    # create payments in org account
    payments_core.update_organisation(
        organisation=event_entry_player.event_entry.event.congress.congress_master.org,
        amount=amount,
        description=f"{event_entry_player.event_entry.event.event_name} - {event_entry_player.player}",
        source="Events",
        log_msg=event_entry_player.event_entry.event.href,
        sub_source="events_callback",
        payment_type="Entry to an event",
        member=who_paid,
    )

    # create payment for user
    payments_core.update_account(
        member=who_paid,
        amount=-amount,
        description=f"{event_entry_player.event_entry.event.event_name} - {event_entry_player.player}",
        source="Events",
        sub_source="events_callback",
        payment_type="Entry to an event",
        log_msg=event_entry_player.event_entry.event.href,
        organisation=event_entry_player.event_entry.event.congress.congress_master.org,
    )


def _update_entries_process_their_system_dollars(event_entries):
    # sourcery skip: extract-method
    """Now process their system dollar transactions (if any)
    We want to batch these up by player and congress so we don't do excessive auto top ups
    """

    # Start by building a dictionary with player then list of event_entry_players to pay for
    event_entries_by_player = {}
    for event_entry in event_entries:
        for event_entry_player in event_entry.evententryplayer_set.all():
            if (
                event_entry_player.payment_type == "their-system-dollars"
                and event_entry_player.payment_status not in ["Paid", "Free"]
            ):
                this_player = event_entry_player.player

                # Add key if not present
                if this_player not in event_entries_by_player:
                    event_entries_by_player[this_player] = []

                # Add event_entry_player to list
                event_entries_by_player[this_player].append(event_entry_player)

    # Now go through each player and do auto top up for full amount if required
    for this_player in event_entries_by_player:
        print("Player is", this_player)
        total_amount_for_player = 0.0
        for event_entry_player in event_entries_by_player[this_player]:
            total_amount_for_player += float(
                event_entry_player.payment_received
            ) - float(event_entry_player.entry_fee)

        # we now have the players total for all events in all congresses. See if this is enough.
        player_balance = payments_core.get_balance(this_player)

        if total_amount_for_player > player_balance:

            # Top up required
            topup_amount = calculate_auto_topup_amount(
                this_player, total_amount_for_player, player_balance
            )
            status, msg = payments_core.auto_topup_member(this_player, topup_amount)

            if not status:
                # Payment failed - abandon for this user. the called functions will handle notifying them
                logger.error(f"Auto top up for {this_player} failed: {msg}")
                continue

        # Check if we need to do an auto top up

        # Now go through and make all of the payments, they should work as there is enough money
        for event_entry_player in event_entries_by_player[this_player]:

            event_entry = event_entry_player.event_entry

            if payment_api_batch(
                member=event_entry_player.player,
                description=event_entry.event.event_name,
                amount=event_entry_player.entry_fee,
                organisation=event_entry_player.event_entry.event.congress.congress_master.org,
                payment_type="Entry to an event",
                book_internals=True,
            ):
                event_entry_player.payment_status = "Paid"
                event_entry_player.entry_complete_date = datetime.now()
                event_entry_player.paid_by = event_entry_player.player
                event_entry_player.payment_received = event_entry_player.entry_fee
                event_entry_player.save()

                EventLog(
                    event=event_entry.event,
                    actor=event_entry_player.player,
                    action=f"Paid with {BRIDGE_CREDITS}",
                    event_entry=event_entry,
                ).save()

                logger.info(
                    f"{event_entry_player.player} paid with their-system-dollars for {event_entry}"
                )
            else:
                logger.warning(
                    f"{event_entry_player.player} payment failed for their-system-dollars for {event_entry}"
                )


def _send_notifications(
    event_entry_players,
    event_entries,
    payment_user,
    triggered_by_team_mate_payment=False,
    team_mate_who_triggered=None,
):
    """Send the notification emails for a particular set of events that has just been paid for

    Args:
        event_entry_players: queryset of EventEntryPlayer. This is a list of people who have
                             just been entered in events and need to be informed
        event_entries: list of event entries that fit with this payment
        payment_user: User. The person who paid
        triggered_by_team_mate_payment: whether this set of notifications was caused by someone other than the
                            primary entrant making a payment (was in the primary entrants basket)

    """

    # First we want to structure our data to be player.congress.event.event_entry_player
    # This gives us the player (who we will send an email to), any congress they are in,
    # any event they are in (in a congress) and who else is in that entry
    struct = _send_notifications_build_struct(event_entry_players)

    # Loop through by player, then congress and send email. 1 email per player per congress
    for player, value in struct.items():
        for congress in value:
            # What payment types are we expecting?
            payment_types = list(
                event_entry_players.filter(event_entry__event__congress=congress)
                .values_list("payment_type", flat=True)
                .distinct()
            )

            # Has this user paid?
            user_owes_money = (
                event_entry_players.filter(player=player)
                .filter(event_entry__event__congress=congress)
                .exclude(payment_status="Paid")
                .exclude(payment_status="Free")
                .exclude(event_entry__entry_status="Cancelled")
                .exists()
            )

            # Use the template to build the email for this user and this congress
            html = loader.render_to_string(
                "events/players/email/player_event_entry.html",
                {
                    "player": player,
                    "events_struct": struct[player][congress],
                    "payment_user": payment_user,
                    "congress": congress,
                    "event": event_entries,
                    "payment_types": payment_types,
                    "user_owes_money": user_owes_money,
                    "triggered_by_team_mate_payment": triggered_by_team_mate_payment,
                    "team_mate_who_triggered": team_mate_who_triggered,
                },
            )

            context = {
                "name": player.first_name,
                "title": f"Event Entry - {congress}",
                "email_body": html,
                "link": "/events/view",
                "link_text": "View Entry",
                "subject": f"Event Entry - {congress}",
            }

            logger.info(f"Sending email to {player}")
            send_cobalt_email_with_template(to_address=player.email, context=context)

    # Notify conveners as well
    _send_notifications_notify_conveners(event_entries)


def _send_notifications_build_struct(event_entry_players):
    """sub function to build the structure to use for emails"""

    struct = {}

    # Create structure
    for event_entry_player in event_entry_players:
        player = event_entry_player.player
        event = event_entry_player.event_entry.event
        congress = event.congress

        # Skip TBA
        if player.id == TBA_PLAYER:
            continue

        # Add if not present struct[player]
        if player not in struct:
            struct[player] = {}

        # Add if not present struct[player][congress] only if player is in this congress
        if congress not in struct[player] and event_entry_players.filter(
            player=player
        ).filter(event_entry__event__congress=congress):
            struct[player][congress] = {}

        # Add if not present struct[player][congress][event] only if player is in this event
        if event not in struct[player][congress] and event_entry_players.filter(
            player=player
        ).filter(event_entry__event=event):
            struct[player][congress][event] = []

    # Populate structure
    for event_entry_player in event_entry_players:
        player = event_entry_player.player
        event = event_entry_player.event_entry.event
        congress = event.congress

        for this_player in struct:
            # Add players if we can
            try:
                struct[this_player][congress][event].append(event_entry_player)
            except KeyError:
                # No place to put this, so we don't need it
                pass

    return struct


def _send_notifications_notify_conveners(event_entries):
    """Notify conveners about an entry coming in"""

    # Notify conveners

    for event_entry in event_entries:
        players = EventEntryPlayer.objects.filter(event_entry=event_entry).order_by(
            "pk"
        )

        html = loader.render_to_string(
            "events/players/email/notify_convener_about_event_entry.html",
            {
                "event_entry": event_entry,
                "players": players,
            },
        )

        event = event_entry.event
        congress = event.congress

        notify_conveners(
            congress,
            event,
            f"New Entry to {event.event_name} in {congress}",
            html,
        )


def _clean_up(payment_user):
    """delete any left over basket items.

    If a user goes to the checkout and then goes to another screen and adds to the basket, then the checkout
    screen is not updated.
    It will checkout and pay for what is shown on the checkout screen (missing the later added items) and those items
    will be checked out too but not paid for.

    The basket isn't intended to be a long term thing.
    """

    # TODO: Use https://github.com/serkanyersen/ifvisible.js or similar to reload the checkout page if a user returns to it

    # Any payments should remove the entry from the shopping basket
    BasketItem.objects.filter(player=payment_user).delete()


def get_basket_for_user(user):
    """called by base html to show basket"""
    return BasketItem.objects.filter(player=user).count()


def get_events(user):
    """called by dashboard to get upcoming events"""

    # get last 50
    event_entry_players = (
        EventEntryPlayer.objects.filter(player=user)
        .exclude(event_entry__entry_status="Cancelled")
        .order_by("-id")[:50]
    )

    # Only include the ones in the future
    upcoming = {}
    unpaid = False
    for event_entry_player in event_entry_players:

        # start_date on event is a function, not a field
        start_date = event_entry_player.event_entry.event.start_date()
        if start_date >= datetime.now().date():
            # Check if still in cart
            in_cart = (
                BasketItem.objects.filter(event_entry=event_entry_player.event_entry)
                .filter(player=user)
                .exists()
            )
            event_entry_player.in_cart = in_cart

            # Check if still in someone elses cart
            in_other_cart = (
                BasketItem.objects.filter(event_entry=event_entry_player.event_entry)
                .exclude(player=user)
                .first()
            )
            if in_other_cart:
                event_entry_player.in_other_cart = in_other_cart.player
                # we do not want to show other player's cart item as unpaid item, in fact we do not want to show them to the player at all
                continue

            # check if unpaid
            if event_entry_player.payment_status == "Unpaid":
                unpaid = True
            upcoming[event_entry_player] = start_date

    upcoming_sorted = {
        key: value for key, value in sorted(upcoming.items(), key=lambda item: item[1])
    }

    return upcoming_sorted, unpaid


def get_conveners_for_congress(congress):
    """get list of conveners for a congress"""

    role = "events.org.%s.edit" % congress.congress_master.org.id
    return rbac_get_users_with_role(role)


def convener_wishes_to_be_notified(congress, convener):
    """Checks with blocked notifications in Notifications to see if this convener wants to know about events that
    happen or not. Currently it is binary (Yes, or No), later it could be extended to check for specific actions"""

    # Get any blocks in place for notifications

    # We want rows for this user, and then either identifier is by Event and model_id is event.id OR
    # identifier is by Org and model_id is org.id

    return not BlockNotification.objects.filter(member=convener).filter(
        (
            (Q(model_id=congress.id) | Q(model_id=None))
            & Q(identifier=BlockNotification.Identifier.CONVENER_EMAIL_BY_EVENT)
        )
        | (
            (Q(model_id=congress.congress_master.org.id) | Q(model_id=None))
            & Q(identifier=BlockNotification.Identifier.CONVENER_EMAIL_BY_ORG)
        )
    )


def notify_conveners(congress, event, subject, email_msg):
    """Let conveners know about things that change."""

    conveners = get_conveners_for_congress(congress)
    link = reverse("events:admin_event_summary", kwargs={"event_id": event.id})

    for convener in conveners:

        # skip if this convener doesn't want the message
        if not convener_wishes_to_be_notified(congress, convener):
            continue

        context = {
            "name": convener.first_name,
            "title": "Convener Msg: " + subject,
            "subject": subject,
            "email_body": f"{email_msg}<br><br>",
            "link": link,
            "link_text": "View Event",
        }

        send_cobalt_email_with_template(to_address=convener.email, context=context)


def events_status_summary():
    """Used by utils status to get the status of events"""

    now = datetime.now().date()
    last_day_date_time = datetime.now() - timedelta(hours=24)
    last_hour_date_time = datetime.now() - timedelta(hours=1)

    active_congresses = (
        Congress.objects.filter(status="Published")
        .filter(start_date__lte=now)
        .filter(end_date__gte=now)
        .count()
    )
    upcoming_congresses = (
        Congress.objects.filter(status="Published").filter(start_date__gt=now).count()
    )
    upcoming_entries = EventEntryPlayer.objects.filter(
        event_entry__event__congress__start_date__gt=now
    ).count()
    entries_last_24_hours = EventEntry.objects.filter(
        first_created_date__gt=last_day_date_time
    ).count()
    entries_last_hour = EventEntry.objects.filter(
        first_created_date__gt=last_hour_date_time
    ).count()

    return {
        "active": active_congresses,
        "upcoming": upcoming_congresses,
        "upcoming_entries": upcoming_entries,
        "entries_last_24_hours": entries_last_24_hours,
        "entries_last_hour": entries_last_hour,
    }


def sort_events_by_start_date(events):
    """Add the start date to a list of events and sort by start date"""

    # add start date and sort by start date
    events_list = {}
    for event in events:
        event.event_start_date = event.start_date()
        if event.event_start_date:
            events_list[event] = event.event_start_date
        else:
            events_list[event] = date(year=1967, month=5, day=3)

    return {
        key: value
        for key, value in sorted(events_list.items(), key=lambda item: item[1])
    }
