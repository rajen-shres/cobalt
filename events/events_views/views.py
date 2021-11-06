""" This module has the views that are used by normal players """

from datetime import datetime
from decimal import Decimal
import uuid
import pytz
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseNotFound
from django.template.loader import render_to_string
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.db import transaction

from logs.views import log_event
from utils.templatetags.cobalt_tags import cobalt_credits
from notifications.views import contact_member
from accounts.models import User, TeamMate
from rbac.core import (
    rbac_user_allowed_for_model,
    rbac_user_has_role,
)
from rbac.views import rbac_forbidden
from payments.payments_views.core import (
    payment_api,
    update_account,
    update_organisation,
)
from cobalt.settings import (
    BRIDGE_CREDITS,
    TIME_ZONE,
    COBALT_HOSTNAME,
    TBA_PLAYER,
    GLOBAL_ORG,
)
from events.models import (
    Congress,
    Category,
    Event,
    Session,
    EventEntry,
    EventEntryPlayer,
    EVENT_PLAYER_FORMAT_SIZE,
    BasketItem,
    PlayerBatchId,
    EventLog,
    Bulletin,
    PartnershipDesk,
    PAYMENT_TYPES,
    CongressDownload,
)
from events.forms import (
    PartnershipForm,
)
from events.events_views.core import (
    events_payments_callback,
    notify_conveners,
    get_basket_for_user,
)

TZ = pytz.timezone(TIME_ZONE)


def home_new(request):
    # check if user has any admin rights to show link to create congress
    width_dict = {
        "defaultContent_width": "4%",
        "congress_start_width": "4%",
        "congress_end_width": "4%",
        "congress_name_width": "24%",
        "run_by_width": "18%",
        "state_width": "4%",
        "event_type_width": "14%",
        "status_width": "6%",
        "actions_width": "14%",
    }
    if request.user.is_authenticated:
        (all_access, some_access) = rbac_user_allowed_for_model(
            request.user, "events", "org", "edit"
        )
        if all_access or some_access:
            admin = True
        else:
            admin = False
            width_dict = {
                "defaultContent_width": "4%",
                "congress_start_width": "4%",
                "congress_end_width": "4%",
                "congress_name_width": "29%",
                "run_by_width": "24%",
                "state_width": "4%",
                "event_type_width": "16%",
                "status_width": "6%",
                "actions_width": "0%",
            }
    else:
        admin = False
        width_dict = {
            "defaultContent_width": "4%",
            "congress_start_width": "4%",
            "congress_end_width": "4%",
            "congress_name_width": "30%",
            "run_by_width": "24%",
            "state_width": "4%",
            "event_type_width": "16%",
            "status_width": "6%",
            "actions_width": "0%",
        }
    return render(
        request, "events/players/home_new.html", {"admin": admin, "config": width_dict}
    )


def home(request):
    """main screen to show congresses

    Can be called without logging in
    """

    congresses = (
        Congress.objects.order_by("start_date")
        .filter(start_date__gte=datetime.now())
        .filter(status="Published")
    )

    if request.user.is_authenticated:

        template = "events/players/home.html"

        # get draft congresses
        draft_congresses = Congress.objects.filter(status="Draft")
        draft_congress_flag = False
        for draft_congress in draft_congresses:
            role = "events.org.%s.edit" % draft_congress.congress_master.org.id
            if rbac_user_has_role(request.user, role):
                draft_congress_flag = True
                break
    else:

        template = "events/players/home_logged_out.html"

        draft_congress_flag = False

    grouped_by_month = {}
    for congress in congresses:

        # Comment field
        if (
            congress.entry_open_date
            and congress.entry_open_date > datetime.now().date()
        ):
            congress.msg = "Entries open on " + congress.entry_open_date.strftime(
                "%d %b %Y"
            )
        elif (
            congress.entry_close_date
            and congress.entry_close_date > datetime.now().date()
        ):
            congress.msg = "Entries close on " + congress.entry_close_date.strftime(
                "%d %b %Y"
            )
        elif (
            congress.entry_close_date
            and congress.entry_close_date <= datetime.now().date()
        ):
            congress.msg = "Congress entries are closed"

        # check access
        if request.user.is_authenticated:
            congress.convener = congress.user_is_convener(request.user)

        # Group congresses by date
        month = congress.start_date.strftime("%B %Y")
        if month in grouped_by_month:
            grouped_by_month[month].append(congress)
        else:
            grouped_by_month[month] = [congress]

    # check if user has any admin rights to show link to create congress
    if request.user.is_authenticated:
        (all_access, some_access) = rbac_user_allowed_for_model(
            request.user, "events", "org", "edit"
        )
        if all_access or some_access:
            admin = True
        else:
            admin = False
    else:
        admin = False

    return render(
        request,
        template,
        {
            "grouped_by_month": grouped_by_month,
            "admin": admin,
            "draft_congress_flag": draft_congress_flag,
        },
    )


def view_congress(request, congress_id, fullscreen=False):
    """basic view of an event.

    Can be called when not logged in.

    Args:
        request(HTTPRequest): standard user request
        congress_id(int): congress to view
        fullscreen(boolean): if true shows just the page, not the standard surrounds
        Also accepts a GET parameter of msg to display for returning from event entry

    Returns:
        page(HTTPResponse): page with details about the event
    """

    congress = get_object_or_404(Congress, pk=congress_id)

    # Which template to use
    if fullscreen:
        master_template = "empty.html"
        template = "events/players/congress.html"
    elif request.user.is_authenticated:
        master_template = "base.html"
        template = "events/players/congress.html"

        # check if published or user has rights
        if congress.status != "Published":
            role = "events.org.%s.edit" % congress.congress_master.org.id
            if not rbac_user_has_role(request.user, role):
                return rbac_forbidden(request, role)
    else:
        template = "events/players/congress_logged_out.html"
        master_template = "empty.html"
        if congress.status != "Published":
            return HttpResponseNotFound("Not published")

    if request.method == "GET" and "msg" in request.GET:
        msg = request.GET["msg"]
    else:
        msg = None

    # We need to build a table for the program from events that has
    # rowspans for the number of days. This is too complex for the
    # template so we build it here.
    #
    # basic structure:
    #
    # <tr><td>Simple Pairs Event<td>Monday<td>12/09/2025 10am<td>Links</tr>
    #
    # <tr><td rowspan=2>Long Teams Event<td>Monday <td>13/09/2025 10am<td rowspan=2>Links</tr>
    # <tr> !Nothing!                    <td>Tuesday<td>14/09/2025 10am !Nothing! </tr>

    # get all events for this congress so we can build the program table
    events = congress.event_set.all()

    if not events:
        return HttpResponseNotFound(
            "No Events set up for this congress. Please notify the convener."
        )

    # add start date and sort by start date
    events_list = {}
    for event in events:
        event.event_start_date = event.start_date()
        if event.event_start_date:
            events_list[event] = event.event_start_date

        events_list_sorted = {
            key: value
            for key, value in sorted(events_list.items(), key=lambda item: item[1])
        }

    # program_list will be passed to the template, each entry is a <tr> element
    program_list = []

    # every day of an event gets its own row so we use rowspan for event name and links
    for event in events_list_sorted:
        program = {}

        # see if user has entered already
        if request.user.is_authenticated:
            program["entry"] = event.already_entered(request.user)
        else:
            program["entry"] = False

        # get all sessions for this event plus days and number of rows (# of days)
        sessions = event.session_set.all()
        days = sessions.distinct("session_date")
        rows = days.count()
        total_entries = (
            EventEntry.objects.filter(event=event)
            .exclude(entry_status="Cancelled")
            .count()
        )  # program["total_entries"] = event
        program[
            "entries_total"
        ] = f"<td rowspan='{rows}'><span class='title'>{total_entries}</td>"
        # day td
        first_row_for_event = True
        for day in days:
            if first_row_for_event:
                entry_fee = cobalt_credits(event.entry_fee)
                program[
                    "event"
                ] = f"<td rowspan='{rows}'><span class='title'>{event.event_name}</td><td rowspan='{rows}'><span class='title'>{entry_fee}</span></td>"
                if program["entry"]:
                    program[
                        "links"
                    ] = f"<td rowspan='{rows}'><a href='/events/congress/event/change-entry/{congress.id}/{event.id}'>View Your Entry</a><br><a href='/events/congress/event/view-event-entries/{congress.id}/{event.id}'>View Entries</a>"
                    if congress.allow_partnership_desk:
                        program[
                            "links"
                        ] += f"<br><a href='/events/congress/event/view-event-partnership-desk/{congress.id}/{event.id}'>Partnership Desk</a>"
                    program["links"] += "</td>"
                else:
                    program[
                        "links"
                    ] = f"<td rowspan='{rows}'><a href='/events/congress/event/enter/{congress.id}/{event.id}'>Enter</a><br><a href='/events/congress/event/view-event-entries/{congress.id}/{event.id}'>View Entries</a>"
                    if congress.allow_partnership_desk:
                        program[
                            "links"
                        ] += f"<br><a href='/events/congress/event/view-event-partnership-desk/{congress.id}/{event.id}'>Partnership Desk</a>"
                    program["links"] += "</td>"
                first_row_for_event = False
            program["day"] = "<td>%s</td>" % day.session_date.strftime("%A")

            # handle multiple times on same day
            # time needs a bit of manipulation as %-I not supported (maybe just Windows?)
            session_start_hour = day.session_start.strftime("%I")
            session_start_hour = "%d" % int(session_start_hour)
            session_minutes = day.session_start.strftime("%M")
            if session_minutes == "00":
                time_str = "%s - %s%s" % (
                    day.session_date.strftime("%d-%m-%Y"),
                    session_start_hour,
                    day.session_start.strftime("%p"),
                )
            else:
                time_str = "%s - %s:%s" % (
                    day.session_date.strftime("%d-%m-%Y"),
                    session_start_hour,
                    day.session_start.strftime("%M%p"),
                )

            times = Session.objects.filter(
                event__pk=day.event.id, session_date=day.session_date
            ).order_by("session_start")

            for time in times[1:]:
                session_start_hour = time.session_start.strftime("%I")
                session_start_hour = "%d" % int(session_start_hour)
                session_minutes = time.session_start.strftime("%M")
                if session_minutes == "00":
                    time_str = "%s & %s%s" % (
                        time_str,
                        session_start_hour,
                        time.session_start.strftime("%p"),
                    )
                else:
                    time_str = "%s & %s:%s" % (
                        time_str,
                        session_start_hour,
                        time.session_start.strftime("%M%p"),
                    )

            program["time"] = "<td>%s</td>" % time_str.lower()  # AM -> pm

            program_list.append(program)
            program = {}

    # Get bulletins
    bulletins = Bulletin.objects.filter(congress=congress).order_by("-pk")

    # Get downloads
    downloads = CongressDownload.objects.filter(congress=congress).order_by("pk")

    return render(
        request,
        template,
        {
            "congress": congress,
            "template": master_template,
            "program_list": program_list,
            "bulletins": bulletins,
            "downloads": downloads,
            "msg": msg,
        },
    )


def _checkout_perform_action(request):
    """sub function for the checkout screen, also called directly if only one item in cart"""

    # Need to mark the entries that this is covering. The payment call is asynchronous so
    # we can't just load all the open basket_entries when we come back or more could have been
    # added.

    # Get list of event_entry_player records to include.
    event_entries = BasketItem.objects.filter(player=request.user).values_list(
        "event_entry"
    )
    event_entry_players = (
        EventEntryPlayer.objects.filter(event_entry__in=event_entries)
        .exclude(payment_status="Paid")
        .exclude(payment_status="Free")
        .filter(payment_type="my-system-dollars")
        .distinct()
    )
    # players that are using club pp to pay are pending payments not unpaid
    # unpaid would prompt the player to pay for event which is not desired here
    event_entry_player_club_pp = (
        EventEntryPlayer.objects.filter(event_entry__in=event_entries)
        .filter(payment_type="off-system-pp")
        .distinct()
    )
    for event_entry in event_entry_player_club_pp:
        event_entry.payment_status = "Pending Manual"
        event_entry.save()

    unique_id = str(uuid.uuid4())

    # map this user (who is paying) to the batch id
    PlayerBatchId(player=request.user, batch_id=unique_id).save()

    # Get total amount
    amount = event_entry_players.aggregate(Sum("entry_fee"))

    if amount["entry_fee__sum"]:  # something for Payments to do

        for event_entry_player in event_entry_players:

            event_entry_player.batch_id = unique_id
            event_entry_player.save()

            # Log it
            EventLog(
                event=event_entry_player.event_entry.event,
                actor=request.user,
                action=f"Checkout for event entry {event_entry_player.event_entry.id} for {event_entry_player.player}",
                event_entry=event_entry_player.event_entry,
            ).save()

        return payment_api(
            request=request,
            member=request.user,
            description="Congress Entry",
            amount=amount["entry_fee__sum"],
            route_code="EVT",
            route_payload=unique_id,
            url=reverse("events:enter_event_success"),
            url_fail=reverse("events:enter_event_payment_fail"),
            payment_type="Entry to an event",
            book_internals=False,
        )

    else:  # no payment required go straight to the callback

        events_payments_callback("Success", unique_id, None)
        messages.success(
            request, "Entry successful", extra_tags="cobalt-message-success"
        )
        return redirect("events:enter_event_success")


@login_required()
def checkout(request):
    """Checkout view - make payments, get details"""

    basket_items = BasketItem.objects.filter(player=request.user)

    if request.method == "POST":
        return _checkout_perform_action(request)

    # Not a POST, build the form

    # Get list of event_entry_player records to include.
    event_entries = BasketItem.objects.filter(player=request.user).values_list(
        "event_entry"
    )
    event_entry_players = (
        EventEntryPlayer.objects.filter(event_entry__in=event_entries).exclude(
            payment_status="Paid"
        )
        #        .exclude(payment_status="Free")
    )

    # get totals per congress
    congress_total = {}
    total_today = Decimal(0)
    total_entry_fee = Decimal(0)

    for event_entry_player in event_entry_players:

        total_entry_fee += event_entry_player.entry_fee
        congress = event_entry_player.event_entry.event.congress

        if congress in congress_total:
            congress_total[congress]["entry_fee"] += event_entry_player.entry_fee
            if event_entry_player.payment_type == "my-system-dollars":
                congress_total[congress]["today"] += event_entry_player.entry_fee
                total_today += event_entry_player.entry_fee
            else:
                congress_total[congress]["later"] += event_entry_player.entry_fee

        else:
            congress_total[congress] = {"entry_fee": event_entry_player.entry_fee}
            if event_entry_player.payment_type == "my-system-dollars":
                congress_total[congress]["today"] = event_entry_player.entry_fee
                total_today += event_entry_player.entry_fee
                congress_total[congress]["later"] = Decimal(0.0)
            else:
                congress_total[congress]["later"] = event_entry_player.entry_fee
                congress_total[congress]["today"] = Decimal(0.0)

    grouped_by_congress = {}
    for event_entry_player in event_entry_players:

        congress = event_entry_player.event_entry.event.congress

        data = {
            "event_entry_player": event_entry_player,
            "entry_fee": congress_total[congress]["entry_fee"],
            "today": congress_total[congress]["today"],
            "later": congress_total[congress]["later"],
        }

        if congress in grouped_by_congress:
            grouped_by_congress[congress].append(data)
        else:
            grouped_by_congress[congress] = [data]

    # The name basket_items is used by the base template so use a different name
    return render(
        request,
        "events/players/checkout.html",
        {
            "grouped_by_congress": grouped_by_congress,
            "total_today": total_today,
            "total_entry_fee": total_entry_fee,
            "total_outstanding": total_entry_fee - total_today,
            "basket_items_list": basket_items,
        },
    )


@login_required()
def view_events(request):
    """View Events you are entered into"""

    # get event entries with event entry player entries for this user
    event_entries_list = (
        EventEntry.objects.filter(evententryplayer__player=request.user).exclude(
            entry_status="Cancelled"
        )
    ).values_list("id")

    # get events where event_entries_list is entered
    events = Event.objects.filter(evententry__in=event_entries_list)

    # Only include the ones in the future
    event_dict = {}
    for event in events:
        start_date = event.start_date()
        if start_date >= datetime.now().date():
            event.entry_status = event.entry_status(request.user)
            event_dict[event] = start_date

    # sort by start date
    event_list = {
        key: value
        for key, value in sorted(event_dict.items(), key=lambda item: item[1])
    }

    # check for pending payments
    pending_payments = (
        EventEntryPlayer.objects.exclude(payment_status="Paid")
        .exclude(payment_status="Free")
        .exclude(payment_type="off-system-pp")
        .filter(player=request.user)
        .exclude(event_entry__entry_status="Cancelled")
    )

    return render(
        request,
        "events/players/view_events.html",
        {"event_list": event_list, "pending_payments": pending_payments},
    )


@login_required()
@transaction.atomic
def pay_outstanding(request):
    """Pay anything that is not in a status of paid"""

    # Get outstanding payments for this user
    event_entry_players = (
        EventEntryPlayer.objects.exclude(payment_status="Paid")
        .exclude(payment_status="Free")
        .filter(player=request.user)
        .exclude(event_entry__entry_status="Cancelled")
    )

    # redirect if nothing owing
    if not event_entry_players:
        messages.warning(
            request, "You have nothing due to pay", extra_tags="cobalt-message-warning"
        )
        return redirect("events:events")

    # Get total amount
    amount = event_entry_players.aggregate(Sum("entry_fee"))

    # identifier
    unique_id = str(uuid.uuid4())

    # apply identifier to each record
    for event_entry_player in event_entry_players:
        event_entry_player.batch_id = unique_id
        event_entry_player.payment_type = "my-system-dollars"
        event_entry_player.save()

    # Log it
    EventLog(
        event=event_entry_player.event_entry.event,
        actor=request.user,
        action=f"Checkout for {request.user}",
        event_entry=event_entry_player.event_entry,
    ).save()

    # map this user (who is paying) to the batch id
    PlayerBatchId(player=request.user, batch_id=unique_id).save()

    # let payments API handle getting the money
    return payment_api(
        request=request,
        member=request.user,
        description="Congress Entry",
        amount=amount["entry_fee__sum"],
        route_code="EVT",
        route_payload=unique_id,
        url=reverse("events:enter_event_success"),
        payment_type="Entry to an event",
        book_internals=False,
    )


def view_event_entries(request, congress_id, event_id):
    """Screen to show entries to an event"""

    congress = get_object_or_404(Congress, pk=congress_id)
    event = get_object_or_404(Event, pk=event_id)
    entries = (
        EventEntry.objects.filter(event=event)
        .exclude(entry_status="Cancelled")
        .order_by("entry_complete_date")
    )
    entries.prefetch_related("evententryplayer_set")
    categories = Category.objects.filter(event=event).exists()
    date_string = event.print_dates()

    # See if this user is already entered
    try:
        user_entered = (
            EventEntryPlayer.objects.filter(event_entry__event=event)
            .filter(player=request.user)
            .exclude(event_entry__entry_status="Cancelled")
            .exists()
        )
        # TODO: Fix this bare exception!
    except TypeError:
        # may be anonymous
        user_entered = False

    return render(
        request,
        "events/players/view_event_entries.html",
        {
            "congress": congress,
            "event": event,
            "entries": entries,
            "categories": categories,
            "date_string": date_string,
            "user_entered": user_entered,
        },
    )


@login_required()
def enter_event_success(request):
    """url for payments to go to after successful entry"""
    messages.success(
        request,
        "Payment complete. You will receive a confirmation email.",
        extra_tags="cobalt-message-success",
    )
    return view_events(request)


@login_required()
@transaction.atomic
def edit_event_entry(request, congress_id, event_id, edit_flag=None, pay_status=None):
    """edit an event entry

    edit_flag is used to enable edit mode on the screen (default off)
    pay_status is used by the "Pay Now" and "Pay All" buttons as the call
    to payment_api cannot add a success or failure message.
    """

    # Load the event
    event = get_object_or_404(Event, pk=event_id)
    congress = get_object_or_404(Congress, pk=congress_id)

    # find matching event entries
    event_entry_player = (
        EventEntryPlayer.objects.filter(player=request.user)
        .filter(event_entry__event=event)
        .exclude(event_entry__entry_status="Cancelled")
        .first()
    )
    if event_entry_player:
        event_entry = event_entry_player.event_entry
    else:
        # see if primary_entrant
        event_entry = (
            EventEntry.objects.filter(primary_entrant=request.user)
            .exclude(entry_status="Cancelled")
            .filter(event=event)
            .first()
        )
        if not event_entry:
            # not entered so redirect
            return redirect(
                "events:enter_event", event_id=event.id, congress_id=congress_id
            )

    # add a flag to the event_players to identify players 5 and 6
    event_entry_players = EventEntryPlayer.objects.filter(
        event_entry=event_entry
    ).order_by("first_created_date")

    pay_count = 0
    for count, event_entry_player in enumerate(event_entry_players, start=1):
        if count > 4:
            event_entry_player.extra_player = True
        # check payment outstanding so we can show a Pay All button if mmore than 1
        if event_entry_player.entry_fee - event_entry_player.payment_received > 0:
            pay_count += 1

    pay_all = bool(pay_count >= 2)

    # Check if still in basket
    in_basket = BasketItem.objects.filter(event_entry=event_entry).count()

    # Optional bits

    # see if event has categories
    categories = Category.objects.filter(event=event)

    # if we got a free format question that will already be on the event
    # We can handle that in the HTML

    # check if pay_status was set and add a message
    if pay_status:
        if pay_status == "success":
            messages.success(
                request,
                "Payment successful",
                extra_tags="cobalt-message-success",
            )
        elif pay_status == "fail":
            messages.error(
                request,
                "Payment failed",
                extra_tags="cobalt-message-error",
            )

    # valid payment methods
    payment_methods = congress.get_payment_methods()

    return render(
        request,
        "events/players/edit_event_entry.html",
        {
            "event": event,
            "congress": congress,
            "event_entry": event_entry,
            "event_entry_players": event_entry_players,
            "categories": categories,
            "edit_flag": edit_flag,
            "in_basket": in_basket,
            "pay_all": pay_all,
            "payment_methods": payment_methods,
        },
    )


@login_required()
@transaction.atomic
def delete_event_entry(request, event_entry_id):
    """Delete an entry to an event"""

    event_entry = get_object_or_404(EventEntry, pk=event_entry_id)

    # check if already cancelled
    if event_entry.entry_status == "Cancelled":
        error = "This entry is already in a cancelled state."
        title = "This entry is already cancelled"
        return render(
            request, "events/players/error.html", {"title": title, "error": error}
        )

    # check if in future
    if event_entry.event.start_date() < datetime.now().date():
        error = "You cannot change an entry after the start date of the event."
        title = "This Event has already started"
        return render(
            request, "events/players/error.html", {"title": title, "error": error}
        )

    # check if passed the automatic refund date
    if (
        event_entry.event.congress.automatic_refund_cutoff
        and event_entry.event.congress.automatic_refund_cutoff < datetime.now().date()
    ):
        error = "You need to contact the tournament organiser directly to make any changes to this entry."
        title = "It is too near to the start of this event"
        return render(
            request, "events/players/error.html", {"title": title, "error": error}
        )

    event_entry_players = EventEntryPlayer.objects.filter(event_entry=event_entry)

    event_entry_players_me = event_entry_players.filter(player=request.user)

    if not event_entry_players_me and event_entry.primary_entrant != request.user:
        error = """You are not the person who made this entry or one of the players.
                   You cannot change this entry."""

        title = "You do not have permission"
        return render(
            request, "events/players/error.html", {"title": title, "error": error}
        )

    # get total paid
    amount = event_entry_players.aggregate(Sum("payment_received"))
    total = amount["payment_received__sum"]

    # check if still in basket
    basket_item = BasketItem.objects.filter(event_entry=event_entry).first()

    if request.method == "POST":

        # This was never a real entry - delete everything
        if basket_item:
            EventLog(
                event=event_entry.event,
                actor=request.user,
                action="Deleted event from cart",
            ).save()
            messages.success(
                request,
                "Event deleted from shopping cart",
                extra_tags="cobalt-message-success",
            )
            basket_item.delete()
            event_entry.delete()

            log_event(
                user=request.user,
                severity="INFO",
                source="Events",
                sub_source="events_delete_from_basket",
                message=f"Entry into {event_entry.event} by {request.user.href} deleted from basket",
            )

            return redirect("events:view_events")

        event_entry.entry_status = "Cancelled"
        event_entry.save()

        EventLog(
            event=event_entry.event,
            actor=request.user,
            action=f"Event entry {event_entry.id} cancelled",
            event_entry=event_entry,
        ).save()

        log_event(
            user=request.user.full_name,
            severity="INFO",
            source="Events",
            sub_source="events_delete_entry",
            message=f"Entry into {event_entry.event.href} by {request.user.href} deleted",
        )

        messages.success(
            request,
            f"Event entry for {event_entry.event} deleted",
            extra_tags="cobalt-message-success",
        )

        # Notify conveners
        player_string = f"<table><tr><td><b>Name</b><td><b>{GLOBAL_ORG} No.</b><td><b>Payment Method</b><td><b>Status</b></tr>"
        PAYMENT_TYPES_DICT = dict(PAYMENT_TYPES)
        for event_entry_player in event_entry_players:
            payment_type_str = PAYMENT_TYPES_DICT.get(
                event_entry_player.payment_type, event_entry_player.payment_type
            )
            player_string += f"<tr><td>{event_entry_player.player.full_name}<td>{event_entry_player.player.system_number}<td>{payment_type_str}<td>{event_entry_player.payment_status}</tr>"
        player_string += "</table>"
        message = "Entry cancelled.<br><br> %s" % player_string
        notify_conveners(
            event_entry.event.congress,
            event_entry.event,
            f"Entry cancelled to {event_entry.event.event_name}",
            message,
        )

        # dict of people getting money and what they are getting
        refunds = {}

        # list of people getting cancelled
        cancelled = []

        # Update records and return paid money
        for event_entry_player in event_entry_players:

            # check for refunds
            amount = float(event_entry_player.payment_received)
            if amount > 0.0:
                event_entry_player.payment_received = Decimal(0)
                event_entry_player.save()

                amount_str = "%.2f credits" % amount

                # Check for blank paid_by - can happen if manually edited
                if not event_entry_player.paid_by:
                    event_entry_player.paid_by = event_entry_player.player

                # Check for TBA - if set electrocute the Convener and pay to primary entrant
                if event_entry_player.paid_by.id == TBA_PLAYER:
                    event_entry_player.paid_by = event_entry.primary_entrant

                # create payments in org account
                update_organisation(
                    organisation=event_entry.event.congress.congress_master.org,
                    amount=-amount,
                    description=f"Refund to {event_entry_player.paid_by} for {event_entry.event.event_name}",
                    source="Events",
                    log_msg=f"Refund to {event_entry_player.paid_by.href} for {event_entry.event.href}",
                    sub_source="refund",
                    payment_type="Refund",
                    member=event_entry_player.paid_by,
                )

                # create payment for member
                update_account(
                    organisation=event_entry.event.congress.congress_master.org,
                    amount=amount,
                    description=f"Refund for {event_entry.event}",
                    source="Events",
                    log_msg=f"Refund from {event_entry.event.congress.congress_master.org} for {event_entry.event.event_name}",
                    sub_source="refund",
                    payment_type="Refund",
                    member=event_entry_player.paid_by,
                )

                # Log it
                EventLog(
                    event=event_entry.event,
                    actor=request.user,
                    action=f"Refund of {amount_str} to {event_entry_player.paid_by}",
                    event_entry=event_entry,
                ).save()

                log_event(
                    user=request.user,
                    severity="INFO",
                    source="Events",
                    sub_source="events_refund",
                    message=f"Refund of {amount_str} to {event_entry_player.player.href} for {event_entry_player.event_entry.event.href}",
                )

                messages.success(
                    request,
                    f"Refund of {amount_str} to {event_entry_player.paid_by} successful",
                    extra_tags="cobalt-message-success",
                )

                # record refund amount
                if event_entry_player.paid_by in refunds:
                    refunds[event_entry_player.paid_by] += amount
                else:
                    refunds[event_entry_player.paid_by] = amount

            # also record players getting cancelled
            if event_entry_player.player not in cancelled:
                cancelled.append(event_entry_player.player)

        # new loop, refunds have been made so notify people
        for member in refunds:

            # Notify users

            # tailor message to recipient
            if member == request.user:
                start_msg = "You have"
            else:
                start_msg = f"{request.user.full_name} has"

            # cancelled and refunds are not necessarily the same
            # someone can enter an event and then be swapped out
            if member in cancelled:
                msg = (
                    f"{start_msg} cancelled your entry to {event_entry.event}.<br><br>"
                )
                cancelled.remove(member)  # already taken care of
            else:
                msg = f"{start_msg} cancelled an entry to {event_entry.event} which you paid for.<br><br>"

            msg += f"You have been refunded {refunds[member]} credits.<br><br>"

            context = {
                "name": member.first_name,
                "title": "Event Entry - %s Cancelled" % event_entry.event.congress,
                "email_body": msg,
                "host": COBALT_HOSTNAME,
                "link": "/events/view",
                "link_text": "View Entry",
            }

            html_msg = render_to_string("notifications/email.html", context)

            # send
            contact_member(
                member=member,
                msg="Entry to %s" % event_entry.event.congress,
                contact_type="Email",
                html_msg=html_msg,
                link="/events/view",
                subject="Entry Cancelled - %s" % event_entry.event,
            )

        # There can be people left on cancelled who didn't pay for their entry - let them know
        for member in cancelled:

            if member == request.user:
                msg = f"You have cancelled your entry to {event_entry.event}.<br><br>"
            else:
                msg = f"{request.user.full_name} has cancelled your entry to {event_entry.event}.<br><br>"

            context = {
                "name": member.first_name,
                "title": "Event Entry - %s Cancelled" % event_entry.event.congress,
                "email_body": msg,
                "host": COBALT_HOSTNAME,
                "link": "/events/view",
                "link_text": "View Entry",
            }

            html_msg = render_to_string("notifications/email.html", context)

            # send
            contact_member(
                member=member,
                msg="Entry to %s" % event_entry.event.congress,
                contact_type="Email",
                html_msg=html_msg,
                link="/events/view",
                subject="Entry Cancelled - %s" % event_entry.event,
            )

        return redirect("events:view_events")

    return render(
        request,
        "events/players/delete_event_entry.html",
        {
            "event_entry": event_entry,
            "event_entry_players": event_entry_players,
            "total": total,
            "basket_item": basket_item,
        },
    )


@login_required()
def third_party_checkout_player(request, event_entry_player_id):
    """Used by edit entry screen to pay for a single other player in the team"""

    event_entry_player = get_object_or_404(EventEntryPlayer, pk=event_entry_player_id)

    event_entry_players_me = EventEntryPlayer.objects.filter(
        event_entry=event_entry_player.event_entry
    ).filter(player=request.user)

    if (
        not event_entry_players_me
        and event_entry_player.event_entry.primary_entrant != request.user
    ):
        error = """You are not the person who made this entry or one of the players.
                   You cannot change this entry."""

        title = "You do not have permission"
        return render(
            request, "events/players/error.html", {"title": title, "error": error}
        )

    # check amount
    amount = float(event_entry_player.entry_fee - event_entry_player.payment_received)

    if amount > 0:
        unique_id = str(uuid.uuid4())

        # map this user (who is paying) to the batch id
        PlayerBatchId(player=request.user, batch_id=unique_id).save()

        event_entry_player.batch_id = unique_id
        event_entry_player.payment_type = "my-system-dollars"
        event_entry_player.save()

        # make payment
        return payment_api(
            request=request,
            member=request.user,
            description="Congress Entry",
            amount=amount,
            route_code="EVT",
            route_payload=unique_id,
            url=reverse(
                "events:edit_event_entry",
                kwargs={
                    "event_id": event_entry_player.event_entry.event.id,
                    "congress_id": event_entry_player.event_entry.event.congress.id,
                    "edit_flag": 1,
                    "pay_status": "success",
                },
            ),
            url_fail=reverse(
                "events:edit_event_entry",
                kwargs={
                    "event_id": event_entry_player.event_entry.event.id,
                    "congress_id": event_entry_player.event_entry.event.congress.id,
                    "edit_flag": 1,
                    "pay_status": "fail",
                },
            ),
            payment_type="Entry to an event",
            book_internals=False,
        )

    else:
        error = """You have tried to pay for an entry, but there is nothing owing. Don't worry, everything seems fine.
                """
        title = "Nothing owing"
        return render(
            request, "events/players/error.html", {"title": title, "error": error}
        )


@login_required()
def third_party_checkout_entry(request, event_entry_id):
    """Used by edit entry screen to pay for all outstanding fees on an entry"""

    event_entry = get_object_or_404(EventEntry, pk=event_entry_id)

    event_entry_players_me = EventEntryPlayer.objects.filter(
        event_entry=event_entry
    ).filter(player=request.user)

    # check for association with entry
    if not event_entry_players_me and event_entry.primary_entrant != request.user:
        error = """You are not the person who made this entry or one of the players.
                   You cannot change this entry."""

        title = "You do not have permission"
        return render(
            request, "events/players/error.html", {"title": title, "error": error}
        )

    # check for cancelled
    if event_entry.entry_status == "Cancelled":
        error = "This entry has been cancelled. You cannot change this entry."
        title = "Cancelled Entry"
        return render(
            request, "events/players/error.html", {"title": title, "error": error}
        )

    # check amount
    event_entry_players = EventEntryPlayer.objects.filter(event_entry=event_entry)
    amount = 0.0
    for event_entry_player in event_entry_players:
        amount += float(
            event_entry_player.entry_fee - event_entry_player.payment_received
        )

    if amount > 0:

        unique_id = str(uuid.uuid4())

        # map this user (who is paying) to the batch id
        PlayerBatchId(player=request.user, batch_id=unique_id).save()

        for event_entry_player in event_entry_players:
            if (
                event_entry_player.payment_received - event_entry_player.entry_fee == 0
            ):  # player had already paid don't do anything
                continue
            event_entry_player.batch_id = unique_id
            event_entry_player.payment_type = "my-system-dollars"
            event_entry_player.save()

        # make payment
        return payment_api(
            request=request,
            member=request.user,
            description="Congress Entry",
            amount=amount,
            route_code="EVT",
            route_payload=unique_id,
            url=reverse(
                "events:edit_event_entry",
                kwargs={
                    "event_id": event_entry_player.event_entry.event.id,
                    "congress_id": event_entry_player.event_entry.event.congress.id,
                    "edit_flag": 1,
                    "pay_status": "success",
                },
            ),
            url_fail=reverse(
                "events:edit_event_entry",
                kwargs={
                    "event_id": event_entry_player.event_entry.event.id,
                    "congress_id": event_entry_player.event_entry.event.congress.id,
                    "edit_flag": 1,
                    "pay_status": "fail",
                },
            ),
            payment_type="Entry to an event",
            book_internals=False,
        )


@login_required()
def enter_event_payment_fail(request):
    """payment required auto top up which failed"""

    error = "Auto top up failed. We were unable to process your transaction."
    title = "Payment Failed"
    return render(
        request, "events/players/error.html", {"title": title, "error": error}
    )


def enter_event_form(event, congress, request):
    """build the form part of the enter_event view. Its not a Django form,
    we build our own as the validation won't work with a dynamic form
    and we are validating on the client side anyway.
    """

    our_form = []

    # get payment types for this congress
    pay_methods = congress.get_payment_methods()

    # Get team mates for this user - exclude anyone entered already
    all_team_mates = TeamMate.objects.filter(user=request.user)
    team_mates_list = all_team_mates.values_list("team_mate")
    entered_team_mates = (
        EventEntryPlayer.objects.filter(event_entry__event=event)
        .exclude(event_entry__entry_status="Cancelled")
        .filter(player__in=team_mates_list)
        .values_list("player")
    )
    team_mates = all_team_mates.exclude(team_mate__in=entered_team_mates)

    name_list = [(0, "Search..."), (TBA_PLAYER, "TBA")]
    for team_mate in team_mates:
        item = (team_mate.team_mate.id, "%s" % team_mate.team_mate.full_name)
        name_list.append(item)

    # set values for player0 (the user)
    entry_fee, discount, reason, description = event.entry_fee_for(request.user)

    payment_selected = pay_methods[0]
    entry_fee_pending = ""
    entry_fee_you = entry_fee

    player0 = {
        "id": request.user.id,
        "payment_choices": pay_methods.copy(),
        "payment_selected": payment_selected,
        "name": request.user.full_name,
        "name_choices": name_list,
        "entry_fee_you": "%s" % entry_fee_you,
        "entry_fee_pending": "%s" % entry_fee_pending,
    }

    # add another option for everyone except the current user
    if congress.payment_method_system_dollars:
        pay_methods.append(("other-system-dollars", "Ask them to pay"))

    # set values for other players
    team_size = EVENT_PLAYER_FORMAT_SIZE[event.player_format]
    min_entries = team_size
    if team_size == 6:
        min_entries = 4
    for ref in range(1, team_size):

        payment_selected = pay_methods[0]
        name_selected = None
        entry_fee = None

        # only ABF dollars go in the you column
        if payment_selected == "my-system-dollars":
            entry_fee_you = entry_fee
            entry_fee_pending = ""
        else:
            entry_fee_you = ""
            entry_fee_pending = entry_fee

        if payment_selected == "their-system-dollars":
            augment_payment_types = [
                ("their-system-dollars", f"Their {BRIDGE_CREDITS}")
            ]
        else:
            augment_payment_types = []

        item = {
            "player_no": ref,
            "payment_choices": pay_methods + augment_payment_types,
            "payment_selected": payment_selected,
            "name_choices": name_list,
            "name_selected": name_selected,
            "entry_fee_you": entry_fee_you,
            "entry_fee_pending": entry_fee_pending,
        }

        our_form.append(item)

    # Start time of event
    sessions = Session.objects.filter(event=event).order_by(
        "session_date", "session_start"
    )
    event_start = sessions.first()

    # use reason etc from above to see if discounts apply
    alert_msg = None

    if reason == "Early discount":
        date_field = event.congress.early_payment_discount_date.strftime("%d/%m/%Y")
        alert_msg = [
            "Early Entry Discount",
            "You qualify for an early discount if you enter now. You will save %s on this event. Discount valid until %s."
            % (cobalt_credits(discount), date_field),
        ]

    if reason == "Youth discount":
        alert_msg = [
            "Youth Discount",
            "You qualify for a youth discount for this event. A saving of %s."
            % cobalt_credits(discount),
        ]

    if reason == "Youth+Early discount":
        alert_msg = [
            "Youth and Early Discount",
            "You qualify for a youth discount as well as an early entry discount for this event. A saving of %s."
            % cobalt_credits(discount),
        ]

    # categories
    categories = Category.objects.filter(event=event)

    return render(
        request,
        "events/players/enter_event.html",
        {
            "player0": player0,
            "our_form": our_form,
            "congress": congress,
            "event": event,
            "categories": categories,
            "sessions": sessions,
            "event_start": event_start,
            "alert_msg": alert_msg,
            "discount": discount,
            "description": description,
            "min_entries": min_entries,
        },
    )


@login_required()
def enter_event(request, congress_id, event_id):
    """enter an event"""

    # Load the event
    event = get_object_or_404(Event, pk=event_id)
    congress = get_object_or_404(Congress, pk=congress_id)

    # Check if already entered
    if event.already_entered(request.user):
        return redirect(
            "events:edit_event_entry", event_id=event.id, congress_id=event.congress.id
        )

    # Check if entries are open
    if not event.is_open():
        return render(request, "events/players/event_closed.html", {"event": event})

    # Check if full
    if event.is_full():
        return render(request, "events/players/event_full.html", {"event": event})

    # Check if draft
    if congress.status != "Published":
        return render(request, "events/players/event_closed.html", {"event": event})

    # check if POST.
    # Note: this works a bit differently to most forms in Cobalt.
    #       We build our own form and use client side code to validate and
    #       modify it.
    #       This will work unless someone has
    #       deliberately bypassed the client side validation in which case we
    #       don't mind failing with an error.

    if request.method == "POST":

        # create event_entry
        event_entry = EventEntry()
        event_entry.event = event
        event_entry.primary_entrant = request.user
        event_entry.comment = request.POST.get("comment", None)

        # see if we got a category
        category = request.POST.get("category", None)
        if category:
            event_entry.category = get_object_or_404(Category, pk=category)

        # see if we got a free format answer
        answer = request.POST.get("free_format_answer", None)
        if answer:
            event_entry.free_format_answer = answer[:60]

        # see if we got a team name
        team_name = request.POST.get("team_name", None)
        if team_name:
            event_entry.team_name = team_name

        event_entry.save()

        # Log it
        EventLog(
            event=event,
            actor=event_entry.primary_entrant,
            action=f"Event entry {event_entry.id} created",
            event_entry=event_entry,
        ).save()

        # add to basket
        basket_item = BasketItem()
        basket_item.player = request.user
        basket_item.event_entry = event_entry
        basket_item.save()

        # Get players from form
        #    players = {0: request.user}
        #    player_payments = {0: request.POST.get("player0_payment")}
        players = {}
        player_payments = {}

        for p_id in range(0, 6):
            p_string = f"player{p_id}"
            ppay_string = f"player{p_id}_payment"
            if p_string in request.POST:
                p_string_value = request.POST.get(p_string)
                if p_string_value != "":
                    players[p_id] = get_object_or_404(User, pk=int(p_string_value))
                    player_payments[p_id] = request.POST.get(ppay_string)
                # regardless of what we get sent - 5th and 6th players are free
                if p_id > 3:
                    player_payments[p_id] = "Free"

        # validate
        if (event.player_format == "Pairs" and len(players) != 2) or (
            event.player_format == "Teams" and len(players) < 4
        ):
            print("invalid number of entries")
            return

        # create player entries
        for p_id in range(len(players)):

            event_entry_player = EventEntryPlayer()
            event_entry_player.event_entry = event_entry
            event_entry_player.player = players[p_id]
            event_entry_player.payment_type = player_payments[p_id]
            entry_fee, discount, reason, description = event.entry_fee_for(
                event_entry_player.player
            )
            if p_id < 4:
                event_entry_player.entry_fee = entry_fee
                event_entry_player.reason = reason
            else:
                event_entry_player.entry_fee = 0
                event_entry_player.reason = "Team > 4"
                event_entry_player.payment_status = "Free"

            # set payment status depending on payment type
            if event_entry_player.payment_status not in [
                "Paid",
                "Free",
            ] and event_entry_player.payment_type in [
                "bank-transfer",
                "cash",
                "cheque",
            ]:
                event_entry_player.payment_status = "Pending Manual"
            event_entry_player.save()

            # Log it
            EventLog(
                event=event,
                actor=event_entry.primary_entrant,
                action=f"Event entry player {event_entry_player.id} created for {event_entry_player.player}",
                event_entry=event_entry,
            ).save()

        if "now" in request.POST:
            # if only one thing in basket, go straight to checkout
            if get_basket_for_user(request.user) == 1:
                return _checkout_perform_action(request)
            else:
                return redirect("events:checkout")

        else:  # add to cart and keep shopping
            msg = "Added to your cart"
            return redirect(
                f"/events/congress/view/{event.congress.id}?msg={msg}#program"
            )

    else:
        return enter_event_form(event, congress, request)


@login_required()
def view_event_partnership_desk(request, congress_id, event_id):
    """Show the partnership desk for an event"""

    event = get_object_or_404(Event, pk=event_id)

    partnerships = PartnershipDesk.objects.filter(event=event)

    # admins can see private entries
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    admin = rbac_user_has_role(request.user, role)

    if partnerships.filter(player=request.user):
        already = True
    else:
        already = False

    return render(
        request,
        "events/players/view_event_partnership_desk.html",
        {
            "partnerships": partnerships,
            "event": event,
            "admin": admin,
            "already": already,
        },
    )


@login_required()
def partnership_desk_signup(request, congress_id, event_id):
    """sign up for the partnership desk"""

    event = get_object_or_404(Event, pk=event_id)

    if request.method == "POST":

        form = PartnershipForm(request.POST)

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Partnership request accepted. Look out for emails from potential partners.",
                extra_tags="cobalt-message-success",
            )
            return redirect(
                "events:view_event_partnership_desk",
                event_id=event.id,
                congress_id=event.congress.id,
            )
        else:
            print(form.errors)
    else:

        form = PartnershipForm()

    return render(
        request,
        "events/players/partnership_desk_signup.html",
        {"form": form, "event": event},
    )
