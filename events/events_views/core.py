from datetime import datetime, timedelta, date

from django.db.models import Q
from django.template import loader
from django.template.loader import render_to_string
from django.urls import reverse

import payments.payments_views.core as payments_core  # circular dependency
from cobalt.settings import COBALT_HOSTNAME, BRIDGE_CREDITS, GLOBAL_ORG
from events.models import PAYMENT_TYPES
from logs.views import log_event
from notifications.models import BlockNotification
from notifications.views import (
    CobaltEmail,
    contact_member_and_queue_email,
    send_cobalt_email_with_template,
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


def events_payments_secondary_callback(status, route_payload, tran):
    """This gets called when a payment has been made for us.

    We supply the route_payload when we ask for the payment to be made and
    use it to update the status of payments.

    This is for the case where a secondary user (not the person making
    the initial entry) has made their payment."""

    log_event(
        user="Unknown",
        severity="INFO",
        source="Events",
        sub_source="events_payments_secondary_callback",
        message=f"Secondary Callback - Status: {status} route_payload: {route_payload}",
    )

    if status == "Success":
        # get name of person who made the entry
        primary_entrant = (
            EventEntryPlayer.objects.filter(batch_id=route_payload)
            .first()
            .event_entry.primary_entrant
        )

        event_entry_players = _get_event_entry_players_from_payload(route_payload)
        event_entries = _get_event_entries_for_event_entry_players(event_entry_players)
        _update_entries(event_entry_players, primary_entrant)
        _clean_up(event_entries)


def events_payments_callback(status, route_payload):
    """This gets called when a payment has been made for us.

    We supply the route_payload when we ask for the payment to be made and
    use it to update the status of payments.

    This gets called when the primary user who is entering the congress
    has made a payment.

    We can use the route_payload to find the payment_user (who entered and paid)
    as well as to find all of the EventEntryPlayer records that have been paid for if this was successful.

    We also need to notify everyone who has been entered which will include people who were not
    paid for by this payment. For that we use the basket of the primary user, which we then empty.

    """

    if status != "Success":
        return

    # Find who is making this payment
    player_batch_id = PlayerBatchId.objects.filter(batch_id=route_payload).first()

    # catch error
    if player_batch_id is None:
        log_event(
            user="Unknown",
            severity="CRITICAL",
            source="Events",
            sub_source="events_payments_callback",
            message=f"No matching player for route_payload: {route_payload}",
        )
        return

    payment_user = player_batch_id.player
    player_batch_id.delete()

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
        event_entry_players.order_by("event_entry")
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
        # this could be a partial payment
        amount = event_entry_player.entry_fee - event_entry_player.payment_received

        event_entry_player.payment_status = "Paid"
        event_entry_player.payment_received = event_entry_player.entry_fee
        event_entry_player.paid_by = payment_user
        event_entry_player.entry_complete_date = datetime.now()
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
            member=payment_user,
        )

        # create payment for user
        payments_core.update_account(
            member=payment_user,
            amount=-amount,
            description=f"{event_entry_player.event_entry.event.event_name} - {event_entry_player.player}",
            source="Events",
            sub_source="events_callback",
            payment_type="Entry to an event",
            log_msg=event_entry_player.event_entry.event.href,
            organisation=event_entry_player.event_entry.event.congress.congress_master.org,
        )


def _update_entries_process_their_system_dollars(event_entries):
    """Now process their system dollar transactions (if any)"""

    for event_entry in event_entries:
        for event_entry_player in event_entry.evententryplayer_set.all():
            if (
                event_entry_player.payment_type == "their-system-dollars"
                and event_entry_player.payment_status not in ["Paid", "Free"]
            ):
                payments_core.payment_api(
                    request=None,
                    member=event_entry_player.player,
                    description=event_entry.event.event_name,
                    amount=event_entry_player.entry_fee,
                    organisation=event_entry_player.event_entry.event.congress.congress_master.org,
                    payment_type="Entry to an event",
                )
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


def _send_notifications(event_entry_players, event_entries, payment_user):
    """Send the notification emails for a particular set of events that has just been paid for

    Args:
        event_entry_players: queryset of EventEntryPlayer. This is a list of people who have
                             just been entered in events and need to be informed
        payment_user: User. The person who paid

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
                    "payment_types": payment_types,
                    "user_owes_money": user_owes_money,
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
            "-pk"
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
