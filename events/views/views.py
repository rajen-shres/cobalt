""" This module has the views that are used by normal players """
import calendar
from datetime import datetime, date, timedelta
from decimal import Decimal
import uuid
import pytz
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseNotFound, HttpResponse
from django.template import loader
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Q
from django.db import transaction
from django.utils import timezone

from organisations.models import Organisation
from payments.views.payments_api import payment_api_interactive
from utils.templatetags.cobalt_tags import cobalt_credits
from notifications.views.core import (
    send_cobalt_email_with_template,
)
from accounts.models import User, TeamMate
from rbac.core import (
    rbac_user_allowed_for_model,
    rbac_user_has_role,
)
from rbac.views import rbac_forbidden
from payments.views.core import (
    update_account,
    update_organisation,
)
from cobalt.settings import (
    BRIDGE_CREDITS,
    TIME_ZONE,
    TBA_PLAYER,
    ABF_STATES,
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
    CongressDownload,
    CONGRESS_TYPES,
)
from events.forms import (
    PartnershipForm,
)
from events.views.core import (
    events_payments_primary_callback,
    notify_conveners,
    get_basket_for_user,
)
from utils.utils import cobalt_paginator

TZ = pytz.timezone(TIME_ZONE)


def congress_listing(request, reverse_list=False):
    """Show list of events

    reverse_list is used to show historic data

    """

    # get states from settings
    states = [state_list[1] for state_list in ABF_STATES.values()]
    states.sort()

    # If not logged in, show different view
    if not request.user.is_authenticated:
        return congress_listing_logged_out(request)

    # Hardcode the venue types. We don't match with the database.
    # People want to filter by online or face to face, not mixed
    congress_venue_types = [("O", "Online"), ("F", "Face-to-Face")]

    return render(
        request,
        "events/players/congress_listing.html",
        {
            "states": states,
            "congress_types": CONGRESS_TYPES,
            "congress_venue_types": congress_venue_types,
            "reverse_list": reverse_list,
        },
    )


def congress_listing_logged_out(request):
    """Congress view when logged out"""

    # Get today
    date_now = date.today()

    congresses = (
        Congress.objects.filter(
            Q(start_date__gte=date_now) | (Q(end_date__gte=date_now))
        )
        .filter(status="Published")
        .select_related("congress_master__org")
        .order_by("start_date")
    )

    month_list = {}
    for congress in congresses:
        month = congress.start_date.strftime("%B %Y")
        if month not in month_list:
            month_list[month] = []
        month_list[month].append(congress)

    return render(
        request,
        "events/players/congress_listing_logged_out.html",
        {"month_list": month_list},
    )


def congress_listing_data_htmx(request):
    """Returns the data for the events listing page.

    There is a limited number of future events, so we just return them all.

    For historic events, we will get a much larger list, so we paginate it but loading 6 months at a time.

    """

    # default values - only used going backwards, but needed for template call
    date_string = None
    show_back_arrow = None
    show_forward_arrow = None

    # Get any parameters from the form
    state = request.POST.get("state")
    congress_type = request.POST.get("congress_type")
    congress_venue_type = request.POST.get("congress_venue_type")
    congress_search_string = request.POST.get("congress_search_string")

    # Reverse list means we want the historic date (closed events, going backwards)
    reverse_list = request.POST.get("reverse_list")

    # Optional - what was the last date we showed the user
    last_data_date = request.POST.get("last_data_date")

    # Optional - does user want to go further back or come forward
    where_to_go = request.POST.get("where_to_go")

    # Get today
    date_now = date.today()

    if reverse_list:
        # We are going backwards
        (
            congresses,
            date_string,
            show_back_arrow,
            show_forward_arrow,
            last_data_date,
        ) = congress_listing_data_backwards(last_data_date, where_to_go, date_now)

    else:
        # Going forwards, show everything
        congresses = (
            Congress.objects.filter(
                Q(start_date__gte=date_now) | (Q(end_date__gte=date_now))
            )
            .filter(status="Published")
            .select_related("congress_master__org")
            .order_by("start_date")
        )

    # Now add modifiers for the queryset
    if state != "All":
        congresses = congresses.filter(congress_master__org__state=state)

    if congress_type != "All":
        congresses = congresses.filter(congress_type=congress_type)

    if congress_venue_type != "All":
        # If user searches for face-to-face or online also show mixed
        if congress_venue_type == "F":
            congresses = congresses.filter(congress_venue_type__in=["F", "M"])
        if congress_venue_type == "O":
            congresses = congresses.filter(congress_venue_type__in=["O", "M"])

    if congress_search_string:
        congresses = congresses.filter(
            Q(name__icontains=congress_search_string)
            | Q(congress_master__org__name__icontains=congress_search_string)
        )

    # We want to order the congresses into months to put in boxes
    month_list = {}
    for congress in congresses:
        month = congress.start_date.strftime("%B %Y")
        if month not in month_list:
            month_list[month] = []
        month_list[month].append(congress)

    return render(
        request,
        "events/players/congress_listing_data_htmx.html",
        {
            "month_list": month_list,
            "last_data_date": last_data_date,
            "show_back_arrow": show_back_arrow,
            "show_forward_arrow": show_forward_arrow,
            "date_string": date_string,
            "reverse_list": reverse_list,
        },
    )


def congress_listing_data_backwards(last_data_date, where_to_go, date_now):
    """sub to handle going backwards

    Args:
        last_data_date(str): date used for last display, can be None
        where_to_go(str): "back", "forward" or None
        date_now(date): date today

    Returns:
        congresses(queryset): Queryset of Congress objects to show
        date_string(str): string to display to user representing this date range
        show_back_arrow(bool): show the back arrow
        show_forward_arrow(bool): show forward arrow
        last_data_date(str): UPDATED date string for this data set - returned to us later

    """

    # default arrows
    show_forward_arrow = False

    if last_data_date:
        # Not on page 1
        show_forward_arrow = True

        if where_to_go == "back":
            # Get end date - one month earlier
            year = int(last_data_date.split("-")[0])
            month = int(last_data_date.split("-")[1]) - 1
            if month == 0:
                year -= 1
                month = 12
            ref_date_end = date(year, month, calendar.monthrange(year, month)[1])

        else:
            # Get end date - 12 months earlier
            year = int(last_data_date.split("-")[0]) + 1
            month = int(last_data_date.split("-")[1]) + 1
            if month == 13:
                year -= 1
                month = 12

            # If we are back at the start, handle that
            if date_now.month == month and date_now.year == year:
                ref_date_end = date_now
                show_forward_arrow = False
            else:
                ref_date_end = date(year, month, calendar.monthrange(year, month)[1])

    else:
        # first page of the reverse view, end on today
        ref_date_end = date_now
        month = int(ref_date_end.strftime("%m"))
        year = int(ref_date_end.strftime("%Y"))

        # Get the previous 6 months
    month -= 6
    if month < 1:
        year -= 1
        month += 12

    # set the start of the period we are looking at and last_data_date, so we get this returned to us if user wants more
    ref_date_start = date(year, month, 1)
    last_data_date = ref_date_start.strftime("%Y-%m")

    congresses = (
        Congress.objects.filter(
            start_date__lt=ref_date_end, start_date__gte=ref_date_start
        )
        .filter(status="Published")
        .select_related("congress_master__org")
        .order_by("-start_date")
    )

    # Check if we have more data
    ref_date_day_before = ref_date_start - timedelta(days=1)
    show_back_arrow = bool(
        Congress.objects.filter(start_date__lt=ref_date_day_before)
        .filter(status="Published")
        .exists()
    )

    if ref_date_end == date_now:
        date_string = f"Yesterday back to {ref_date_start:%B %Y}"
    else:
        date_string = f"{ref_date_end:%B %Y} back to {ref_date_start:%B %Y}"

    return congresses, date_string, show_back_arrow, show_forward_arrow, last_data_date


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

    # get all events for this congress so we can build the program table.
    # We use list_priority_order to set the order within events on the same day if required
    events = congress.event_set.all().order_by("-list_priority_order")

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

        # We want the first session for each day
        days = sessions.order_by("session_date", "session_start").distinct(
            "session_date"
        )
        rows = days.count()
        total_entries = (
            EventEntry.objects.filter(event=event)
            .exclude(entry_status="Cancelled")
            .count()
        )
        program["event_id"] = event.id
        program["event_name"] = event.event_name
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
                    ] = f"<td rowspan='{rows}'><a href='/events/congress/event/change-entry/{congress.id}/{event.id}' class='btn btn-block btn-sm btn-primary'>View Your Entry</a>"
                else:
                    # See if taking entries
                    is_open, reason = event.is_open_with_reason()

                    if is_open:

                        program[
                            "links"
                        ] = f"<td rowspan='{rows}'><a href='/events/congress/event/enter/{congress.id}/{event.id}' class='btn btn-block btn-sm btn-success'>Enter</a>"

                    else:
                        program[
                            "links"
                        ] = f"<td rowspan='{rows}' class='text-center'>{reason}"

                # Handle common parts of links
                program["links"] += (
                    f"<a href='/events/congress/event/view-event-entries/{congress.id}/{event.id}' "
                    "class='btn btn-block btn-sm btn-info'>View Entries</a>"
                )
                # Logged out needs extra breaks
                if not request.user.is_authenticated:
                    program["links"] = program["links"].replace("</a>", "</a><br>")

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

    # Check for admin rights to show edit/manage buttons
    if request.user.is_authenticated:
        is_admin = rbac_user_has_role(
            request.user, f"events.org.{congress.congress_master.org.id}.edit"
        )
        # try global admin
        if not is_admin:
            is_admin = rbac_user_has_role(request.user, "events.org.edit")
    else:
        is_admin = False

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
            "is_admin": is_admin,
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

        return payment_api_interactive(
            request=request,
            member=request.user,
            description="Congress Entry",
            amount=amount["entry_fee__sum"],
            route_code="EVT",
            route_payload=unique_id,
            next_url=reverse("events:enter_event_success"),
            # url_fail=reverse("events:enter_event_payment_fail"),
            book_internals=False,
            payment_type="Entry to an event",
        )

    else:  # no payment required go straight to the callback

        events_payments_primary_callback("Success", unique_id)
        messages.success(
            request, "Entry successful", extra_tags="cobalt-message-success"
        )
        return redirect("events:enter_event_success")


@login_required()
def checkout(request):
    """Checkout view - make payments, get details"""

    basket_items = BasketItem.objects.filter(player=request.user).exclude(
        event_entry__entry_status="Cancelled"
    )

    if request.method == "POST":
        return _checkout_perform_action(request)

    # Not a POST, build the form

    # Get list of event_entry_player records to include.
    event_entries = basket_items.values_list("event_entry")
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
        return redirect("events:view_events")

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
    return payment_api_interactive(
        request=request,
        member=request.user,
        description="Congress Entry",
        amount=amount["entry_fee__sum"],
        route_code="EVT",
        route_payload=unique_id,
        next_url=reverse("events:enter_event_success"),
        payment_type="Entry to an event",
        book_internals=False,
    )


# This was the updated version - not released due to testing differences and shortage of time

# def view_event_entries(request, congress_id, event_id):
#     """Screen to show entries to an event"""
#
#     congress = get_object_or_404(Congress, pk=congress_id)
#     event = get_object_or_404(Event, pk=event_id)
#     event_entries = (
#         EventEntry.objects.filter(event=event)
#         .exclude(entry_status="Cancelled")
#         .select_related("category")
#         .order_by("entry_complete_date")
#     )
#
#     # identify this users entry
#     my_entry = None
#     event_entry_players = (
#         EventEntryPlayer.objects.filter(event_entry__event=event)
#         .select_related("player", "event_entry")
#         .order_by("pk")
#     )
#
#     if request.user.is_authenticated:
#         for player in event_entry_players:
#             if player.player == request.user:
#                 my_entry = player.event_entry
#                 break
#
#     # Loop through event entries and add event entry players in order they entered
#     # We use the values we already have from the database to prevent additional calls
#     for event_entry in event_entries:
#         event_entry.this_event_entry_players = []
#         for event_entry_player in event_entry_players:
#             if event_entry_player.event_entry == event_entry:
#                 event_entry.this_event_entry_players.append(event_entry_player)
#
#     categories = Category.objects.filter(event=event).exists()
#     date_string = event.print_dates()
#
#     # See if this user is already entered
#     try:
#         user_entered = (
#             EventEntryPlayer.objects.filter(event_entry__event=event)
#             .filter(player=request.user)
#             .exclude(event_entry__entry_status="Cancelled")
#             .exists()
#         )
#     except TypeError:
#         # may be anonymous
#         user_entered = False
#
#     return render(
#         request,
#         "events/players/view_event_entries.html",
#         {
#             "congress": congress,
#             "event": event,
#             "event_entries": event_entries,
#             "categories": categories,
#             "date_string": date_string,
#             "user_entered": user_entered,
#             "my_entry": my_entry,
#         },
#     )


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
    # entries.prefetch_related("evententryplayer_player_set")

    # identify this users entry
    if request.user.is_authenticated:
        for entry in entries:
            # Commenting this out for now as doesn't go to the entry it is intended to go to
            # if entry.primary_entrant == request.user:
            #     entry.my_entry = True
            #     continue
            for player in entry.evententryplayer_set.all():
                if player.player == request.user:
                    entry.my_entry = True

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
def edit_event_entry(
    request, congress_id=None, event_id=None, pay_status=None, event_entry_id=None
):
    """edit an event entry

    pay_status is used by the "Pay Now" and "Pay All" buttons as the call
    to payment_api cannot add a success or failure message.

    event_entry_id is provided for when someone is editing an entry that they created that doesn't have them as a player

    """

    # If we got an event entry, then try to load it. Will only be for primary_entrant
    if event_entry_id:
        event_entry = get_object_or_404(EventEntry, pk=event_entry_id)
        # Check this is legitimate
        if event_entry.primary_entrant != request.user:
            return HttpResponse(
                f"Invalid request - attempt to edit EventEntry:{event_entry} which has a Primary Entrant of {event_entry.primary_entrant} by another player {request.user}"
            )
        # Load the event
        event = event_entry.event
        congress = event.congress

    # Otherwise, try to load entry
    else:
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

    pay_all = pay_count >= 2

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
            "in_basket": in_basket,
            "pay_all": pay_all,
            "payment_methods": payment_methods,
        },
    )


@login_required()
@transaction.atomic
def delete_event_entry(request, event_entry_id):
    """Delete an entry to an event"""

    # Get data
    event_entry = get_object_or_404(EventEntry, pk=event_entry_id)
    event_entry_players = EventEntryPlayer.objects.filter(
        event_entry=event_entry
    ).order_by("-pk")

    # Validate
    status, response = _delete_event_entry_validation(request, event_entry)
    if not status:
        return response

    # get total paid
    amount = event_entry_players.aggregate(Sum("payment_received"))
    total = amount["payment_received__sum"]

    # check if still in basket
    basket_item = BasketItem.objects.filter(event_entry=event_entry).first()

    # handle a post request
    if request.method == "POST":
        return _delete_event_entry_handle_post(
            request, event_entry, event_entry_players, basket_item
        )

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


def _delete_event_entry_validation(request, event_entry):
    """Perform validation for the delete entry screen"""

    # check if already cancelled
    if event_entry.entry_status == "Cancelled":
        error = "This entry is already in a cancelled state."
        title = "This entry is already cancelled"
        return False, render(
            request, "events/players/error.html", {"title": title, "error": error}
        )

    # check if in future
    if event_entry.event.start_date() < datetime.now().date():
        error = "You cannot change an entry after the start date of the event."
        title = "This Event has already started"
        return False, render(
            request, "events/players/error.html", {"title": title, "error": error}
        )

    # check if passed the automatic refund date
    if (
        event_entry.event.congress.automatic_refund_cutoff
        and event_entry.event.congress.automatic_refund_cutoff < datetime.now().date()
    ):
        error = "You need to contact the tournament organiser directly to make any changes to this entry."
        title = "It is too near to the start of this event"
        return False, render(
            request, "events/players/error.html", {"title": title, "error": error}
        )

    # Check if this is their entry to edit
    if not event_entry.user_can_change(request.user):
        error = """You are not the person who made this entry or one of the players.
                   You cannot change this entry."""

        title = "You do not have permission"
        return False, render(
            request, "events/players/error.html", {"title": title, "error": error}
        )

    # If we got here it is okay
    return True, True


def _delete_event_entry_handle_post(
    request, event_entry, event_entry_players, basket_item
):
    """Handle a user posting a delete request to the delete event entry screen"""

    # If in basket and no payments then delete
    if basket_item and not event_entry_players.exclude(payment_received=0).exists():
        return _delete_event_entry_handle_post_basket(event_entry, request, basket_item)

    event_entry.entry_status = "Cancelled"
    event_entry.save()

    EventLog(
        event=event_entry.event,
        actor=request.user,
        action=f"Event entry {event_entry.id} cancelled",
        event_entry=event_entry,
    ).save()

    messages.success(
        request,
        f"Event entry for {event_entry.event} deleted",
        extra_tags="cobalt-message-success",
    )

    # Notify conveners
    _delete_event_entry_handle_post_notify_conveners(
        request, event_entry, event_entry_players
    )

    # Handle refunds
    refunds, cancelled = _delete_event_entry_handle_post_refunds(
        request, event_entry, event_entry_players
    )

    # Notify people
    _delete_event_entry_handle_post_notify_users(
        request, event_entry, event_entry_players, refunds, cancelled
    )

    return redirect("events:view_events")


def _delete_event_entry_handle_post_basket(event_entry, request, basket_item):
    """Delete an entry that was in the basket and had no payments made"""

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

    return redirect("events:view_events")


def _delete_event_entry_handle_post_notify_conveners(
    request, event_entry, event_entry_players
):
    """Notify conveners when entry is deleted"""

    html = loader.render_to_string(
        "events/players/email/notify_convener_about_event_entry_cancellation.html",
        {
            "event_entry": event_entry,
            "event_entry_players": event_entry_players,
            "user": request.user,
        },
    )

    notify_conveners(
        event_entry.event.congress,
        event_entry.event,
        f"Entry cancelled to {event_entry.event.event_name}",
        html,
    )


def _delete_event_entry_handle_post_refunds(request, event_entry, event_entry_players):
    """Handle refunds to players who withdraw from events"""

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
                payment_type="Refund",
                member=event_entry_player.paid_by,
            )

            # create payment for member
            update_account(
                organisation=event_entry.event.congress.congress_master.org,
                amount=amount,
                description=f"Refund for {event_entry.event}",
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

    return refunds, cancelled


def _delete_event_entry_handle_post_notify_users(
    request, event_entry, event_entry_players, refunds, cancelled
):
    """After the refunds have been done and the entry cancelled we let them know"""

    for member, value in refunds.items():

        # cancelled and refunds are not necessarily the same
        # someone can enter an event and then be swapped out
        if member in cancelled:
            cancelled.remove(member)  # already taken care of

        # skip TBA
        if member.id == TBA_PLAYER:
            continue

        html = loader.render_to_string(
            "events/players/email/player_event_entry_cancellation.html",
            {
                "event_entry": event_entry,
                "event_entry_players": event_entry_players,
                "user": request.user,
                "member": member,
                "value": value,
            },
        )

        context = {
            "name": member.first_name,
            "title": "Event Entry - %s Cancelled" % event_entry.event.congress,
            "email_body": html,
            "link": "/events/view",
            "link_text": "View Congress Entries",
            "subject": "Entry Cancelled - %s" % event_entry.event,
        }

        send_cobalt_email_with_template(to_address=member.email, context=context)

    # There can be people left on cancelled who didn't pay for their entry - let them know
    for member in cancelled:

        # skip TBA
        if member.id == TBA_PLAYER:
            continue

        html = loader.render_to_string(
            "events/players/email/player_event_entry_cancellation.html",
            {
                "event_entry": event_entry,
                "event_entry_players": event_entry_players,
                "user": request.user,
                "member": member,
                "value": 0,
            },
        )

        context = {
            "name": member.first_name,
            "title": "Event Entry - %s Cancelled" % event_entry.event.congress,
            "email_body": html,
            "link": "/events/view",
            "link_text": "View Congress Entries",
            "subject": "Entry Cancelled - %s" % event_entry.event,
            "box_colour": "danger",
        }

        send_cobalt_email_with_template(to_address=member.email, context=context)


@login_required()
def third_party_checkout_player(request, event_entry_player_id):
    """Used by edit entry screen to pay for a single other player in the team"""

    event_entry_player = get_object_or_404(EventEntryPlayer, pk=event_entry_player_id)

    return _third_party_checkout_entry_common(
        request, event_entry_player.event_entry, [event_entry_player]
    )


@login_required()
def third_party_checkout_entry(request, event_entry_id):
    """Used by edit entry screen to pay for all outstanding fees on an entry"""

    event_entry = get_object_or_404(EventEntry, pk=event_entry_id)
    event_entry_players = EventEntryPlayer.objects.filter(event_entry=event_entry)

    return _third_party_checkout_entry_common(request, event_entry, event_entry_players)


def _third_party_checkout_entry_common(request, event_entry, event_entry_players):
    """Takes a list of event_entry_players (or a Queryset, as long as it is iterable and returns EventEntryPlayer)
    for a single event_entry and handles the checkout process for this user to pay for them"""

    # Get this user's event_entry_player object for this event entry if there is one
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
    amount = 0.0
    for event_entry_player in event_entry_players:
        amount += float(
            event_entry_player.entry_fee - event_entry_player.payment_received
        )

    if amount <= 0:
        error = """You have tried to pay for an entry, but there is nothing owing. Don't worry, everything seems fine.
                """
        title = "Nothing owing"
        return render(
            request, "events/players/error.html", {"title": title, "error": error}
        )

    unique_id = str(uuid.uuid4())

    # map this user (who is paying) to the batch id
    PlayerBatchId(player=request.user, batch_id=unique_id).save()

    # add batch id to the event_entry_player objects who are getting paid for
    for event_entry_player in event_entry_players:
        if event_entry_player.payment_received - event_entry_player.entry_fee == 0:
            # player had already paid don't do anything
            continue
        event_entry_player.batch_id = unique_id
        event_entry_player.payment_type = "my-system-dollars"
        event_entry_player.save()

    # make payment
    return payment_api_interactive(
        request=request,
        member=request.user,
        description="Congress Entry",
        amount=amount,
        route_code="EV2",
        route_payload=unique_id,
        next_url=reverse(
            "events:edit_event_entry",
            kwargs={
                "event_id": event_entry.event.id,
                "congress_id": event_entry.event.congress.id,
                "pay_status": "success",
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


def enter_event_non_post_delete(event, congress, request, enter_for_another):
    """Handle a blank entry. Build the page and return to user."""

    our_form = []

    # get payment types for this congress
    pay_methods = congress.get_payment_methods()

    # Get teammates for this user - exclude anyone entered already
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
        item = team_mate.team_mate.id, f"{team_mate.team_mate.full_name}"
        name_list.append(item)

    # set values for player0 (the user)
    entry_fee, discount, reason, description = event.entry_fee_for(request.user)

    payment_selected = pay_methods[0]
    entry_fee_pending = ""
    entry_fee_you = entry_fee

    # Player 0 settings depend upon whether this is the first entry or entering for someone else
    if enter_for_another:

        # Add ask them to pay as an option
        pay_methods_player0 = pay_methods.copy()
        if congress.payment_method_system_dollars:
            pay_methods_player0.append(("other-system-dollars", "Ask them to pay"))

        player0 = {
            "id": TBA_PLAYER,
            "payment_choices": pay_methods_player0,
            "payment_selected": payment_selected,
            "name": "TBA",
            "name_choices": name_list,
            "entry_fee_you": f"{entry_fee_you}",
            "entry_fee_pending": f"{entry_fee_pending}",
        }
    else:
        player0 = {
            "id": request.user.id,
            "payment_choices": pay_methods.copy(),
            "payment_selected": payment_selected,
            "name": request.user.full_name,
            "name_choices": name_list,
            "entry_fee_you": f"{entry_fee_you}",
            "entry_fee_pending": f"{entry_fee_pending}",
        }

    # add another option for everyone except the current user
    if congress.payment_method_system_dollars:
        pay_methods.append(("other-system-dollars", "Ask them to pay"))

    # set values for other players
    team_size = EVENT_PLAYER_FORMAT_SIZE[event.player_format]
    min_entries = team_size
    if team_size == 6:
        min_entries = 4
    name_selected = None
    for ref in range(1, team_size):

        payment_selected = pay_methods[0]
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
            f"You qualify for an early discount if you enter now. You will save {cobalt_credits(discount)} on this event. Discount valid until {date_field}.",
        ]

    if reason == "Youth discount":
        alert_msg = [
            "Youth Discount",
            f"You qualify for a youth discount for this event. A saving of {cobalt_credits(discount)}.",
        ]

    if reason == "Youth+Early discount":
        alert_msg = [
            "Youth and Early Discount",
            f"You qualify for a youth discount as well as an early entry discount for this event. A saving of {cobalt_credits(discount)}.",
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
            "enter_for_another": enter_for_another,
        },
    )


def _get_team_mates_for_event(user, event):
    """Get available team mates for this event and this user"""

    # Get teammates for this user - exclude anyone entered already
    all_team_mates = TeamMate.objects.filter(user=user)
    team_mates_list = all_team_mates.values_list("team_mate")
    entered_team_mates = (
        EventEntryPlayer.objects.filter(event_entry__event=event)
        .exclude(event_entry__entry_status="Cancelled")
        .filter(player__in=team_mates_list)
        .values_list("player")
    )
    return all_team_mates.exclude(team_mate__in=entered_team_mates)


def enter_event_non_post(event, congress, request, enter_for_another):
    """Handle a blank entry. Build the page and return to user."""

    # Start time of event
    event_start = (
        Session.objects.filter(event=event)
        .order_by("session_date", "session_start")
        .first()
    )

    # categories
    categories = Category.objects.filter(event=event)

    return render(
        request,
        "events/players/enter_event_new.html",
        {
            "congress": congress,
            "event": event,
            "categories": categories,
            "event_start": event_start,
            "enter_for_another": enter_for_another,
        },
    )


@login_required()
def enter_event_players_area_htmx(request):
    """builds the entry part of the event entry page"""


def enter_event_post(request, congress, event):
    """Handle a post request to enter an event"""

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
    if team_name and team_name != "":
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

    for p_id in range(6):
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
        return redirect(f"/events/congress/view/{event.congress.id}?msg={msg}#program")


@login_required()
def enter_event(request, congress_id, event_id, enter_for_another=0):
    """enter an event

    Some people want to enter on behalf of their friends so we allow an extra parameter to handle this.

    """

    # Load the event
    event = get_object_or_404(Event, pk=event_id)
    congress = get_object_or_404(Congress, pk=congress_id)

    # Check if already entered or entering for someone else
    if not enter_for_another and event.already_entered(request.user):
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

    if request.method == "POST":
        return enter_event_post(request, congress, event)
    else:
        return enter_event_non_post_delete(event, congress, request, enter_for_another)


@login_required()
def view_event_partnership_desk(request, congress_id, event_id):
    """Show the partnership desk for an event"""

    event = get_object_or_404(Event, pk=event_id)

    partnerships = PartnershipDesk.objects.filter(event=event)

    # admins can see private entries
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    admin = rbac_user_has_role(request.user, role)

    already = bool(partnerships.filter(player=request.user))

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


@login_required()
def show_congresses_for_club_htmx(request):
    """Show upcoming congresses for a club. Called from the club org_profile."""

    club = get_object_or_404(Organisation, pk=request.POST.get("club_id"))

    congresses = Congress.objects.filter(
        congress_master__org=club, status="Published", end_date__gte=timezone.now()
    ).order_by("start_date")

    things = cobalt_paginator(request, congresses)

    hx_post = reverse("events:show_congresses_for_club_htmx")
    hx_vars = f"club_id:{club.id}"
    hx_target = "#club-congresses"

    return render(
        request,
        "events/players/clubs/show_congresses_for_club_htmx.html",
        {
            "things": things,
            "hx_post": hx_post,
            "hx_vars": hx_vars,
            "hx_target": hx_target,
        },
    )


@login_required()
def get_other_entries_to_event_for_user_htmx(request, event_id, this_event_entry_id):

    """
    Get entries for this user in this event which don't include them.
    Required to allow a user to edit entries that they have made which are not their own.

    event_entry_id is the one that calls us, we return all others

    """

    # Get event
    event = get_object_or_404(Event, pk=event_id)

    # Get entries made by this user, where they aren't a player, exclude the one provided
    # Also include entries for this user (not primary)
    entries = (
        # only want entries for this event
        EventEntry.objects.filter(event=event)
        # Not cancelled
        .exclude(entry_status="Cancelled")
        # exclude the provided event_id, this is the one asking for others so they don't want themselves back
        .exclude(pk=this_event_entry_id)
        # primary entrant OR any player
        .filter(
            Q(primary_entrant=request.user) | Q(evententryplayer__player=request.user)
        ).distinct()
    )

    return render(
        request,
        "events/players/get_other_entries_to_event_for_user_htmx.html",
        {"entries": entries},
    )
