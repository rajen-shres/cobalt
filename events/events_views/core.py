from datetime import datetime, timedelta, date

from django.db.models import Q
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
        _update_entries(event_entry_players, primary_entrant)
        _clean_up(event_entry_players)


def events_payments_callback(status, route_payload):
    """This gets called when a payment has been made for us.

    We supply the route_payload when we ask for the payment to be made and
    use it to update the status of payments.

    This gets called when the primary user who is entering the congress
    has made a payment."""

    if status == "Success":
        # Find who is making this payment
        pbi = PlayerBatchId.objects.filter(batch_id=route_payload).first()

        # catch error
        if pbi is None:
            log_event(
                user="Unknown",
                severity="CRITICAL",
                source="Events",
                sub_source="events_payments_callback",
                message=f"No matching player for route_payload: {route_payload}",
            )
            return

        payment_user = pbi.player
        pbi.delete()

        event_entry_players = _get_event_entry_players_from_payload(route_payload)
        _update_entries(event_entry_players, payment_user)
        _send_notifications(payment_user)
        _clean_up(event_entry_players)


def _get_event_entry_players_from_payload(route_payload):
    """Returns the entries that are associated with the route_payload. Route_payload is sent as a paramter
    to Stripe so we when a payment is made we can find the corresponding entries."""

    return EventEntryPlayer.objects.filter(batch_id=route_payload)


def _update_entries(event_entry_players, payment_user):
    """Update the database to reflect changes and make payments for
    other members if we have access."""

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

    # Get all EventEntries for changed EventEntryPlayers
    event_entry_list = (
        event_entry_players.order_by("event_entry")
        .distinct("event_entry")
        .values_list("event_entry")
    )

    event_entries = EventEntry.objects.filter(pk__in=event_entry_list).exclude(
        entry_status="Cancelled"
    )

    # Now process their system dollar transactions - same loop as below but
    # easier to understand as 2 separate bits of code
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

    # Check if EntryEvent is now complete
    for event_entry in event_entries:
        event_entry.check_if_paid()

    return event_entries


def _send_notifications(payment_user):
    """Send the notification emails for a particular set of events that has just been paid for"""

    # Go through the basket and notify people
    # We send one email per congress
    # email_dic will be email_dic[congress][event][player]
    email_dic = {}

    basket_items = BasketItem.objects.filter(player=payment_user)

    for basket_item in basket_items:
        # Get players in event
        players = basket_item.event_entry.evententryplayer_set.all()

        for player in players:
            event = basket_item.event_entry.event
            congress = event.congress
            if congress not in email_dic.keys():
                email_dic[congress] = {}
            if event not in email_dic[congress].keys():
                email_dic[congress][event] = []
            email_dic[congress][event].append(player)

    # now build the emails
    for congress in email_dic:

        # build a list of all players so we can set them each up a custom email
        player_email = {}  # email to send keyed by player
        player_included = {}  # flag for whether player is in this event

        for event in email_dic[congress].keys():
            for player in email_dic[congress][event]:
                if player.player not in player_email.keys():
                    player_email[player.player] = ""
                    player_included[player.player] = False

        # build start of email for this congress
        for player in player_email:
            if player == payment_user:
                player_email[
                    player
                ] = f"""
                    <p>We have received your entry into <b>{congress.name}</b>
                    """
            else:
                player_email[
                    player
                ] = f"""
                    <p>{payment_user.full_name} has entered you into <b>{congress.name}</b>
                    """

            player_email[
                player
            ] += f"""
                hosted by {congress.congress_master.org}.</p>
                <table class="receipt" border="0" cellpadding="0" cellspacing="0">
                <tr><td style='text-align: left'><b>Event</b><td style='text-align:
                left'><b>Players</b><td style='text-align: right'><b>Entry Status</b></tr>
                """

        for event in email_dic[congress].keys():

            sub_msg = (
                f"<tr><td style='text-align: left' class='receipt-figure'>{event.event_name}<td style='text"
                f"-align: left' class='receipt-figure'> "
            )

            for player in email_dic[congress][event]:
                sub_msg += f"{player.player.full_name}<br>"
                player_included[player.player] = True

            sub_msg += f"<td style='text-align: right' class='receipt-figure'>{player.event_entry.entry_status}</tr>"

            # add this row if player is in the event - no point otherwise
            for player in player_email:

                if player_included[player]:
                    player_email[player] += sub_msg
                    player_included[player] = False

        for player in player_email:

            # Close table
            player_email[player] += "</table><br>"

            # Get details
            event_entry_players = (
                EventEntryPlayer.objects.exclude(payment_status="Paid")
                .exclude(payment_status="Free")
                .filter(player=player)
                .filter(event_entry__event__congress=congress)
                .exclude(event_entry__entry_status="Cancelled")
            )

            # Check status
            if event_entry_players.exists():

                # Outstanding payments due. Check for bank and cheque
                if event_entry_players.filter(payment_type="bank-transfer").exists():
                    player_email[player] += (
                        "<p>We are expecting payment by bank transfer.</p><h3>Bank Details</h3> %s<br><br>"
                        % event_entry_players[
                            0
                        ].event_entry.event.congress.bank_transfer_details
                    )

                if event_entry_players.filter(payment_type="cheque").exists():
                    player_email[player] += (
                        "<p>We are expecting payment by cheque.</p><h3>Cheques</h3> %s<br><br>"
                        % event_entry_players[
                            0
                        ].event_entry.event.congress.cheque_details
                    )

                if event_entry_players.filter(payment_type="off-system-pp").exists():
                    player_email[player] += (
                        "<p>We are expecting payment from another pre-paid system. The convener will handle this for "
                        "you.</p><br><br> "
                    )

                player_email[player] += (
                    "You have outstanding payments to make to complete this entry. Click on the button below to view "
                    "your payments. Note that entries are not complete until all payments have been received.<br><br> "
                )
            else:
                player_email[player] += (
                    "Your entries are all paid for however other players in the entry may still need to pay. You can "
                    "see overall entry status above. You have nothing more to do. If you need to view the entry or "
                    "change anything you can use the link below.<br><br> "
                )

            # build email
            context = {
                "name": player.first_name,
                "title": "Event Entry - %s" % congress,
                "email_body": player_email[player],
                "link": "/events/view",
                "link_text": "View Entry",
                "subject": f"Event Entry - {congress}",
            }

            send_cobalt_email_with_template(to_address=player.email, context=context)

    # Notify conveners
    for congress in email_dic:
        for event in email_dic[congress].keys():
            player_string = (
                f"<table><tr><td><b>Name</b><td><b>{GLOBAL_ORG} No.</b><td><b>Payment "
                f"Method</b><td><b>Status</b></tr> "
            )
            for player in email_dic[congress][event]:
                PAYMENT_TYPES_DICT = dict(PAYMENT_TYPES)
                payment_type_str = PAYMENT_TYPES_DICT[player.payment_type]
                player_string += f"<tr><td>{player.player.full_name}<td>{player.player.system_number}<td>{payment_type_str}<td>{player.payment_status}</tr> "
            player_string += "</table>"
            message = "New entry received.<br><br> %s" % player_string

            notify_conveners(
                congress,
                event,
                f"New Entry to {event.event_name} in {event.congress}",
                message,
            )


def _clean_up(event_entry_players):
    """delete any left over basket items"""

    # Check if EntryEvent is now complete
    for event_entry_player in event_entry_players:
        event_entry_player.event_entry.check_if_paid()

        # Any payments should remove the entry from the shopping basket
        # basket = BasketItem.objects.filter(event_entry=event_entry)
        #
        # if basket:
        #     basket.delete()


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


def notify_conveners(
    congress, event, subject, email_msg, notify_msg=None, email_obj=None
):
    """Let conveners know about things that change. This can be called with an optional CobaltEmail object
    in which case it will queue the messages to that. If not provided then it will create its own.
    """

    if not notify_msg:
        notify_msg = subject

    send_it = False
    if not email_obj:
        email_obj = CobaltEmail()
        send_it = True

    conveners = get_conveners_for_congress(congress)
    link = reverse("events:admin_event_summary", kwargs={"event_id": event.id})

    for convener in conveners:

        # skip if this convener doesn't want the message
        if not convener_wishes_to_be_notified(congress, convener):
            continue

        context = {
            "name": convener.first_name,
            "title": "Convener Msg: " + subject,
            "email_body": f"{email_msg}<br><br>",
            "host": COBALT_HOSTNAME,
            "link": link,
            "link_text": "View Event",
        }

        html_msg = render_to_string("notifications/email_with_button.html", context)

        # send
        contact_member_and_queue_email(
            member=convener,
            email_object=email_obj,
            msg=notify_msg,
            html_msg=html_msg,
            link=link,
            subject=subject,
        )

    if send_it:
        email_obj.send()


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
