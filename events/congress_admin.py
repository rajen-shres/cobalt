""" The file has the code relating to a convener managing an existing event """

import csv
from threading import Thread

from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.forms import formset_factory
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.utils import timezone, dateformat
from django.db.models import Sum, Q
from notifications.views import contact_member, send_cobalt_bulk_email, CobaltEmail
from logs.views import log_event
from django.db import transaction
from .models import (
    Congress,
    Category,
    CongressMaster,
    Event,
    Session,
    EventEntry,
    EventEntryPlayer,
    PAYMENT_TYPES,
    EVENT_PLAYER_FORMAT_SIZE,
    BasketItem,
    EventLog,
    EventPlayerDiscount,
    Bulletin,
)
from accounts.models import User, TeamMate
import requests
from .forms import (
    CongressForm,
    NewCongressForm,
    EventForm,
    SessionForm,
    EventEntryPlayerForm,
    RefundForm,
    EventPlayerDiscountForm,
    EmailForm,
    BulletinForm,
    LatestNewsForm,
    OffSystemPPForm,
)
from rbac.core import (
    rbac_user_allowed_for_model,
    rbac_get_users_with_role,
)
from rbac.views import rbac_user_has_role, rbac_forbidden
from .core import events_payments_callback
from payments.core import payment_api, org_balance, update_account, update_organisation
from organisations.models import Organisation
from django.contrib import messages
import uuid
import copy
from cobalt.settings import (
    GLOBAL_ORG,
    GLOBAL_CURRENCY_NAME,
    BRIDGE_CREDITS,
    TIME_ZONE,
    COBALT_HOSTNAME,
    TBA_PLAYER,
)
from datetime import datetime
import itertools
from utils.utils import cobalt_paginator
from django.utils.timezone import make_aware, now, utc
import pytz
from decimal import Decimal
from cobalt.settings import GLOBAL_MPSERVER

TZ = pytz.timezone(TIME_ZONE)


@login_required()
def admin_summary(request, congress_id):
    """Admin View"""

    congress = get_object_or_404(Congress, pk=congress_id)
    events = Event.objects.filter(congress=congress)

    # check access
    role = "events.org.%s.edit" % congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    total = {
        "entries": 0,
        "tables": 0.0,
        "due": Decimal(0),
        "paid": Decimal(0),
        "pending": Decimal(0),
    }

    # calculate summary
    for event in events:
        event_entries = EventEntry.objects.filter(event=event).exclude(
            entry_status="Cancelled"
        )
        event.entries = event_entries.count()
        if event.entry_early_payment_discount:
            event.early_fee = event.entry_fee - event.entry_early_payment_discount
        else:
            event.early_fee = event.entry_fee

        # calculate tables
        players_per_entry = EVENT_PLAYER_FORMAT_SIZE[event.player_format]

        # Teams of 3 - only need 3 to make a table
        if players_per_entry == 3:
            players_per_entry = 4

        # For teams we only have 4 per table
        if event.player_format == "Teams":
            players_per_entry = 4

        event.tables = event.entries * players_per_entry / 4.0

        # remove decimal if not required
        if event.tables == int(event.tables):
            event.tables = int(event.tables)

        # Get the event entry players for this event
        event_entry_list = event_entries.values_list("id")
        event_entry_players = EventEntryPlayer.objects.filter(
            event_entry__in=event_entry_list
        )

        # Total entry fee due
        event.due = event_entry_players.exclude(
            event_entry__entry_status="Cancelled"
        ).aggregate(Sum("entry_fee"))["entry_fee__sum"]
        if event.due is None:
            event.due = Decimal(0)

        event.paid = event_entry_players.exclude(
            event_entry__entry_status="Cancelled"
        ).aggregate(Sum("payment_received"))["payment_received__sum"]
        if event.paid is None:
            event.paid = Decimal(0)

        event.pending = event.due - event.paid

        # update totals
        total["entries"] += event.entries
        total["tables"] += event.tables
        total["due"] += event.due
        total["paid"] += event.paid
        total["pending"] += event.pending

    # fix total formatting
    if total["tables"] == int(total["tables"]):
        total["tables"] = int(total["tables"])

    return render(
        request,
        "events/admin_summary.html",
        {"events": events, "total": total, "congress": congress},
    )


@login_required()
def admin_event_summary(request, event_id):
    """Admin Event View"""

    event = get_object_or_404(Event, pk=event_id)

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    event_entries = (
        EventEntry.objects.filter(event=event)
        .exclude(entry_status="Cancelled")
        .order_by("first_created_date")
    )

    # build summary
    total_received = Decimal(0.0)
    total_outstanding = Decimal(0.0)
    total_entry_fee = Decimal(0.0)

    for event_entry in event_entries:
        event_entry_players = EventEntryPlayer.objects.filter(event_entry=event_entry)
        event_entry.received = Decimal(0.0)
        event_entry.outstanding = Decimal(0.0)
        event_entry.entry_fee = Decimal(0.0)
        event_entry.players = []
        event_entry.status = "Deceased, Alive"
        event_entry.masterpoints = "100,45"

        for event_entry_player in event_entry_players:

            if event_entry_player.payment_received:
                received = event_entry_player.payment_received
            else:
                received = Decimal(0.0)

            event_entry.received += received
            event_entry.outstanding += event_entry_player.entry_fee - received
            event_entry.entry_fee += event_entry_player.entry_fee
            event_entry.players.append(event_entry_player)

            total_received += received
            total_outstanding += event_entry_player.entry_fee - received
            total_entry_fee += event_entry_player.entry_fee

    # check on categories
    categories = Category.objects.filter(event=event).exists()

    return render(
        request,
        "events/admin_event_summary.html",
        {
            "event": event,
            "event_entries": event_entries,
            "total_received": total_received,
            "total_outstanding": total_outstanding,
            "total_entry_fee": total_entry_fee,
            "categories": categories,
        },
    )


@login_required()
def admin_evententry(request, evententry_id):
    """Admin Event Entry View"""

    event_entry = get_object_or_404(EventEntry, pk=evententry_id)
    event = event_entry.event
    congress = event.congress

    role = "events.org.%s.edit" % congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    event_entry_players = EventEntryPlayer.objects.filter(
        event_entry=event_entry
    ).order_by("id")

    event_logs = EventLog.objects.filter(event_entry=event_entry).order_by("-id")

    return render(
        request,
        "events/admin_event_entry.html",
        {
            "event_entry": event_entry,
            "event": event,
            "congress": congress,
            "event_entry_players": event_entry_players,
            "event_logs": event_logs,
        },
    )


@login_required()
def admin_evententryplayer(request, evententryplayer_id):
    """Admin Event Entry Player View"""

    event_entry_player = get_object_or_404(EventEntryPlayer, pk=evententryplayer_id)
    old_user = copy.copy(event_entry_player.player)
    old_entry = copy.copy(event_entry_player)
    print(old_user)
    event = event_entry_player.event_entry.event

    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if request.method == "POST":
        form = EventEntryPlayerForm(request.POST, instance=event_entry_player)
        if form.is_valid():
            new_user = form.cleaned_data["player"]
            form.save()

            # check if event entry payment status has changed
            event_entry_player.event_entry.check_if_paid()

            messages.success(
                request, "Entry updated", extra_tags="cobalt-message-success"
            )

            # Log it
            for changed in form.changed_data:
                old_value = getattr(old_entry, changed)
                new_value = getattr(event_entry_player, changed)
                action = f"Convener Action: Changed {changed} from {old_value} to {new_value} on Entry:{old_entry.id} - {event_entry_player.event_entry}"
                log_action = f"Convener Action: Changed {changed} from {old_value} to {new_value} on Entry:{event_entry_player.event_entry.href}"

                # Don't understand this so hardcoding - other fields work but player doesnt
                if changed == "player":
                    action = f"Convener Action: Changed {changed} from {old_user} to {new_user} on Entry:{old_entry.id} - {event_entry_player.event_entry}"
                    action = f"Convener Action: Changed {changed} from {old_user} to {new_user} on Entry:{event_entry_player.event_entry.href}"

                EventLog(
                    event=event,
                    event_entry=event_entry_player.event_entry,
                    actor=request.user,
                    action=action,
                ).save()

                log_event(
                    user=request.user.href,
                    severity="INFO",
                    source="Events",
                    sub_source="events_admin",
                    message=log_action,
                )

            if new_user != old_user:

                # notify deleted member
                if old_user.id != TBA_PLAYER:
                    context = {
                        "name": old_user.first_name,
                        "title": "Removed from event - %s" % event,
                        "email_body": f"The convener, {request.user.full_name}, has removed you from this event.<br><br>",
                        "host": COBALT_HOSTNAME,
                    }

                    html_msg = render_to_string("notifications/email.html", context)

                    # send
                    contact_member(
                        member=old_user,
                        msg="Removed from - %s" % event,
                        contact_type="Email",
                        html_msg=html_msg,
                        link="/events/view",
                        subject="Removed from - %s" % event,
                    )

                # notify added member
                if new_user.id != TBA_PLAYER:
                    context = {
                        "name": new_user.first_name,
                        "title": "Added to event - %s" % event,
                        "email_body": f"The convener, {request.user.full_name}, has added you to this event.<br><br>",
                        "host": COBALT_HOSTNAME,
                        "link": "/events/view",
                        "link_text": "View Entry",
                    }

                    html_msg = render_to_string(
                        "notifications/email_with_button.html", context
                    )

                    # send
                    contact_member(
                        member=new_user,
                        msg="Added to - %s" % event,
                        contact_type="Email",
                        html_msg=html_msg,
                        link="/events/view",
                        subject="Added to - %s" % event,
                    )

            return redirect(
                "events:admin_evententry",
                evententry_id=event_entry_player.event_entry.id,
            )
    else:
        form = EventEntryPlayerForm(instance=event_entry_player)

    return render(
        request,
        "events/admin_event_entry_player.html",
        {"event_entry_player": event_entry_player, "form": form},
    )


@login_required()
def admin_event_csv(request, event_id):
    """Download a CSV file with details of the entries"""

    event = get_object_or_404(Event, pk=event_id)

    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    # get details
    entries = event.evententry_set.exclude(entry_status="Cancelled").order_by(
        "first_created_date"
    )

    local_dt = timezone.localtime(timezone.now(), TZ)
    today = dateformat.format(local_dt, "Y-m-d H:i:s")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f"attachment; filename={event}.csv"

    writer = csv.writer(response)
    writer.writerow(
        [event.event_name, "Downloaded by %s" % request.user.full_name, today]
    )

    # Event Entry details
    header = [
        "Players",
        "Entry Fee",
        "Received",
        "Outstanding",
        "Status",
        "First Created Date",
        "Entry Complete Date",
    ]

    categories = Category.objects.filter(event=event).exists()

    if categories:
        header.append("Category")

    if event.free_format_question:
        header.append(f"{event.free_format_question}")

    header.append("Player comment")
    header.append("Organiser Notes")
    writer.writerow(header)

    for row in entries:

        players = ""
        received = Decimal(0)
        entry_fee = Decimal(0)

        for player in row.evententryplayer_set.all():
            players += player.player.full_name + " - "
            try:
                received += player.payment_received
            except TypeError:
                pass  # ignore if payment_received is None
            entry_fee += player.entry_fee
        players = players[:-3]

        local_dt = timezone.localtime(row.first_created_date, TZ)
        local_dt2 = timezone.localtime(row.entry_complete_date, TZ)

        this_row = [
            players,
            entry_fee,
            received,
            entry_fee - received,
            row.entry_status,
            dateformat.format(local_dt, "Y-m-d H:i:s"),
            dateformat.format(local_dt2, "Y-m-d H:i:s"),
        ]

        if categories:
            this_row.append(row.category)
        if event.free_format_question:
            this_row.append(row.free_format_answer)

        this_row.append(row.comment)
        this_row.append(row.notes)
        writer.writerow(this_row)

    # Event Entry Player details
    writer.writerow([])
    writer.writerow([])
    writer.writerow(
        [
            "Primary Entrant",
            "Player",
            "Player - First Name",
            "Player - Last Name",
            "Player - Email",
            "Player - contact",
            "Player - Number",
            "Player - Status",
            "Player - masterpoints",
            "Payment Type",
            "Entry Fee",
            "Received",
            "Outstanding",
            "Entry Fee Reason",
            "Payment Status",
        ]
    )

    for entry in entries:
        for row in entry.evententryplayer_set.all():
            if row.payment_received:
                outstanding = row.entry_fee - row.payment_received
            else:
                outstanding = row.entry_fee
            masterpoints, status = get_player_mp_stats(row.player)
            writer.writerow(
                [
                    entry.primary_entrant,
                    row.player,
                    row.player.first_name,
                    row.player.last_name,
                    row.player.email,
                    row.player.mobile,
                    row.player.system_number,
                    status,
                    masterpoints,
                    row.payment_type,
                    row.entry_fee,
                    row.payment_received,
                    outstanding,
                    row.reason,
                    row.payment_status,
                ]
            )

    # Log it
    EventLog(event=event, actor=request.user, action=f"CSV Download of {event}").save()

    return response


@login_required()
def admin_event_csv_scoring(request, event_id):
    """Download a CSV file with info to import to a scoring program"""

    event = get_object_or_404(Event, pk=event_id)

    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    # local_dt = timezone.localtime(timezone.now(), TZ)
    #   today = dateformat.format(local_dt, "Y-m-d H:i:s")

    # get details
    entries = event.evententry_set.exclude(entry_status="Cancelled").order_by(
        "first_created_date"
    )

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f"attachment; filename={event} - Scoring.csv"

    writer = csv.writer(response)
    if event.player_format == "Pairs":
        title = "Pair No"
    else:
        title = "Team No"

    # Event Entry details
    header = [
        title,
        "Name",
        "ABF Number",
        "Player phone",
        "Player Email",
        "Team Name",
        "Category",
        "question",
        "Player comment",
        "Organiser notes",
    ]

    writer.writerow(header)

    count = 1

    for entry in entries:
        entry_line = 1
        for row in entry.evententryplayer_set.all():
            data_row = [
                count,
                row.player.full_name.upper(),
                row.player.system_number,
                row.player.mobile,
                row.player.email,
                row.event_entry.primary_entrant.last_name.upper(),
            ]
            if entry_line == 1:
                data_row.append(entry.category)
                data_row.append(entry.free_format_answer)
                data_row.append(entry.comment)
                data_row.append(entry.notes)
            else:
                data_row.append("")
                data_row.append("")
                data_row.append("")
                data_row.append("")
            writer.writerow(data_row)
            entry_line += 1
        # add extra blank rows for teams if needed
        if event.player_format == "Teams":
            for extra_lines in range(7 - entry_line):
                writer.writerow(
                    [count, "", "", "", "", entry.primary_entrant.last_name.upper()]
                )

        count += 1

    # Log it
    EventLog(
        event=event, actor=request.user, action=f"CSV Download of scoring for {event}"
    ).save()

    return response


@login_required()
def admin_event_offsystem(request, event_id):
    """Handle off system payments such as cheques and bank transfers"""

    event = get_object_or_404(Event, pk=event_id)

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    # get players with manual payment methods
    players = (
        EventEntryPlayer.objects.filter(event_entry__event=event)
        .exclude(
            payment_type__in=[
                "my-system-dollars",
                "their-system-dollars",
                "other-system-dollars",
                "off-system-pp",
            ]
        )
        .exclude(event_entry__entry_status="Cancelled")
    )

    return render(
        request,
        "events/admin_event_offsystem.html",
        {"event": event, "players": players},
    )


@login_required()
def admin_event_offsystem_pp(request, event_id):
    """Handle Club PP system to allow clubs to use their existing PP system as a payment method"""

    event = get_object_or_404(Event, pk=event_id)

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    # get players with pps
    players = (
        EventEntryPlayer.objects.filter(event_entry__event=event)
        .filter(payment_type="off-system-pp")
        .exclude(event_entry__entry_status="Cancelled")
    )

    return render(
        request,
        "events/admin_event_offsystem_pp.html",
        {"event": event, "players": players},
    )


@login_required()
def admin_event_unpaid(request, event_id):
    """Unpaid Report"""

    event = get_object_or_404(Event, pk=event_id)

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    # get players with unpaid entries
    players = (
        EventEntryPlayer.objects.filter(event_entry__event=event)
        .exclude(payment_status="Paid")
        .exclude(payment_status="Free")
        .exclude(event_entry__entry_status="Cancelled")
    )

    return render(
        request,
        "events/admin_event_unpaid.html",
        {"event": event, "players": players},
    )


@login_required()
def admin_players_report(request, event_id):
    """Unpaid Report"""

    event = get_object_or_404(Event, pk=event_id)

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    # get players with unpaid entries
    players = EventEntryPlayer.objects.filter(event_entry__event=event).exclude(
        event_entry__entry_status="Cancelled"
    )
    for player in players:
        player.masterpoint, player.status = get_player_mp_stats(player.player)

    return render(
        request,
        "events/admin_players_report.html",
        {"event": event, "players": players},
    )


def get_player_mp_stats(player):
    """
    Get summary data
    """
    qry = "%s/mps/%s" % (
        GLOBAL_MPSERVER,
        player.system_number,
    )  # player.player.system_number)
    try:
        r = requests.get(qry).json()
    except (
        IndexError,
        requests.exceptions.InvalidSchema,
        requests.exceptions.MissingSchema,
        ConnectionError,
    ):
        r = []

    if len(r) == 0:
        return "Unknown ABF no", "Unknown ABF no"
    is_active = r[0]["IsActive"]
    if is_active == "Y":
        is_active = "Active"
    else:
        is_active = "Inactive"
    return r[0]["TotalMPs"], is_active


@login_required()
def admin_event_log(request, event_id):
    """Show logs for an event"""

    event = get_object_or_404(Event, pk=event_id)

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    logs = EventLog.objects.filter(event=event).order_by("-action_date")

    things = cobalt_paginator(request, logs)

    return render(
        request, "events/admin_event_log.html", {"event": event, "things": things}
    )


@login_required()
def admin_evententry_delete(request, evententry_id):
    """Delete an event entry"""

    event_entry = get_object_or_404(EventEntry, pk=evententry_id)

    # check access
    role = "events.org.%s.edit" % event_entry.event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    event_entry_players = EventEntryPlayer.objects.filter(event_entry=event_entry)

    # We use a formset factory to have multiple players on the same form
    RefundFormSet = formset_factory(RefundForm, extra=0)

    if request.method == "POST":
        refund_form_set = RefundFormSet(data=request.POST)
        if refund_form_set.is_valid():
            for form in refund_form_set:
                player = get_object_or_404(User, pk=form.cleaned_data["player_id"])
                # Check for TBA - if we have a TBA user who has been paid for then
                # a refund is due. Give it to the person who made the entry.
                if player.id == TBA_PLAYER:
                    player = event_entry.primary_entrant
                amount = float(form.cleaned_data["refund"])
                amount_str = "%.2f credits" % amount

                if amount > 0.0:

                    # create payments in org account
                    update_organisation(
                        organisation=event_entry.event.congress.congress_master.org,
                        amount=-amount,
                        description=f"Refund to {player} for {event_entry.event.event_name}",
                        source="Events",
                        log_msg=f"Refund to {player} for {event_entry.event.event_name}",
                        sub_source="refund",
                        payment_type="Refund",
                        member=player,
                    )

                    # create payment for member
                    update_account(
                        organisation=event_entry.event.congress.congress_master.org,
                        amount=amount,
                        description=f"Refund from {event_entry.event.congress.congress_master.org} for {event_entry.event.event_name}",
                        source="Events",
                        log_msg=f"Refund from {event_entry.event.congress.congress_master.org} for {event_entry.event.event_name}",
                        sub_source="refund",
                        payment_type="Refund",
                        member=player,
                    )

                    # update payment records
                    for event_entry_player in event_entry_players:
                        event_entry_player.payment_received = Decimal(0)
                        event_entry_player.save()

                    # Log it
                    EventLog(
                        event=event_entry.event,
                        actor=request.user,
                        action=f"Refund of {amount_str} to {player}",
                        event_entry=event_entry,
                    ).save()
                    messages.success(
                        request,
                        f"Refund of {amount_str} to {player} successful",
                        extra_tags="cobalt-message-success",
                    )

                # Notify member
                email_body = f"""{request.user.full_name} has cancelled your entry to
                                <b>{event_entry.event.event_name}</b> in
                                <b>{event_entry.event.congress.name}.</b><br><br>
                              """
                if amount > 0.0:
                    email_body += f"""A refund of {amount:.2f} credits
                                    has been transferred to your {BRIDGE_CREDITS}
                                    account.<br><br>
                                  """

                email_body += f"Please contact {request.user.first_name} directly if you have any queries.<br><br>"

                context = {
                    "name": player.first_name,
                    "title": "Entry to %s cancelled" % event_entry.event,
                    "email_body": email_body,
                    "host": COBALT_HOSTNAME,
                    "link": "/events/view",
                    "link_text": "View Congresses",
                }

                html_msg = render_to_string(
                    "notifications/email_with_button.html", context
                )

                # send
                contact_member(
                    member=player,
                    msg="Entry to %s cancelled" % event_entry.event.event_name,
                    contact_type="Email",
                    html_msg=html_msg,
                    link="/events/view",
                    subject="Event Entry Cancelled - %s" % event_entry.event,
                )

        # Log it
        EventLog(
            event=event_entry.event,
            actor=request.user,
            action=f"Entry deleted for {event_entry.primary_entrant}",
            event_entry=event_entry,
        ).save()

        event_entry.entry_status = "Cancelled"
        event_entry.save()

        messages.success(
            request, "Entry cancelled", extra_tags="cobalt-message-success"
        )
        return redirect("events:admin_event_summary", event_id=event_entry.event.id)

    else:  # not POST - build summary
        event_entry.received = Decimal(0)
        initial = []

        # we need to default refund per player to who actually paid it, not
        # who was entered. If Fred paid for Bill's entry then Fred should get
        # the refund not Bill

        refund_dict = {}
        for event_entry_player in event_entry_players:
            refund_dict[event_entry_player.player] = Decimal(0)

        for event_entry_player in event_entry_players:
            # check if we have a player who paid
            if event_entry_player.paid_by:

                # maybe this player is no longer part of the team
                if event_entry_player.paid_by not in refund_dict.keys():
                    refund_dict[event_entry_player.paid_by] = Decimal(0)

                refund_dict[
                    event_entry_player.paid_by
                ] += event_entry_player.payment_received

            # Not sure who paid so default it back to the entry name
            else:
                try:
                    refund_dict[
                        event_entry_player.player
                    ] += event_entry_player.payment_received
                except TypeError:
                    pass

        for player_refund in refund_dict.keys():
            event_entry.received += refund_dict[player_refund]

            initial.append(
                {
                    "player_id": player_refund.id,
                    "player": f"{player_refund}",
                    "refund": refund_dict[player_refund],
                }
            )

        refund_form_set = RefundFormSet(initial=initial)

        club = event_entry.event.congress.congress_master.org
        club_balance = org_balance(club)

    return render(
        request,
        "events/admin_event_entry_delete.html",
        {
            "event_entry": event_entry,
            "event_entry_players": event_entry_players,
            "refund_form_set": refund_form_set,
            "club": club,
            "club_balance": club_balance,
        },
    )


@login_required()
def admin_event_player_discount(request, event_id):
    """Manage discounted entry to events"""

    event = get_object_or_404(Event, pk=event_id)

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    event_player_discounts = EventPlayerDiscount.objects.filter(event=event)

    if request.method == "POST":
        form = EventPlayerDiscountForm(request.POST)
        if form.is_valid():

            player = form.cleaned_data["player"]
            reason = form.cleaned_data["reason"]

            already = EventPlayerDiscount.objects.filter(
                event=event, player=player
            ).count()

            if already:
                messages.error(
                    request,
                    f"There is already a discount for {player}",
                    extra_tags="cobalt-message-error",
                )

            entered = (
                EventEntryPlayer.objects.filter(event_entry__event=event, player=player)
                .exclude(event_entry__entry_status="Cancelled")
                .exists()
            )

            if entered:
                messages.error(
                    request,
                    f"{player} has already entered this event. Update the entry to change the entry fee.",
                    extra_tags="cobalt-message-error",
                )

            else:

                entry_fee = form.cleaned_data["entry_fee"]
                event_player_discount = EventPlayerDiscount()
                event_player_discount.player = player
                event_player_discount.admin = request.user
                event_player_discount.event = event
                event_player_discount.reason = reason
                event_player_discount.entry_fee = entry_fee
                event_player_discount.save()

                # Log it
                EventLog(
                    event=event,
                    actor=request.user,
                    action=f"Added discount of {entry_fee} for {player} in {event}",
                ).save()

                log_event(
                    user=request.user.href,
                    severity="INFO",
                    source="Events",
                    sub_source="events_admin",
                    message=f"Added discount of {entry_fee} for {player.href} in {event.href}",
                )
                messages.success(
                    request, "Entry added", extra_tags="cobalt-message-success"
                )

    # check if player is entered
    for event_player_discount in event_player_discounts:
        if event_player_discount.event.already_entered(event_player_discount.player):
            event_player_discount.status = "Entered - "

            # check status of entry
            event_entry_player = (
                EventEntryPlayer.objects.filter(event_entry__event=event)
                .filter(player=event_player_discount.player)
                .exclude(event_entry__entry_status="Cancelled")
                .first()
            )
            event_player_discount.status += "%s" % event_entry_player.payment_status
            event_player_discount.event_entry_player_id = event_entry_player.id
        else:
            event_player_discount.status = "Not Entered"

    form = EventPlayerDiscountForm()

    return render(
        request,
        "events/admin_event_player_discount.html",
        {
            "event": event,
            "event_player_discounts": event_player_discounts,
            "form": form,
        },
    )


@login_required()
def admin_event_email(request, event_id):
    """Email all entrants to an event"""

    event = get_object_or_404(Event, pk=event_id)

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    # who will receive this
    recipients_qs = EventEntryPlayer.objects.filter(event_entry__event=event).exclude(
        event_entry__entry_status="Cancelled"
    )

    return _admin_email_common(request, recipients_qs, event.congress, event)


@login_required()
def admin_congress_email(request, congress_id):
    """Email all entrants to an entire congress"""

    congress = get_object_or_404(Congress, pk=congress_id)

    # check access
    role = "events.org.%s.edit" % congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    # who will receive this
    recipients_qs = EventEntryPlayer.objects.filter(
        event_entry__event__congress=congress
    ).exclude(event_entry__entry_status="Cancelled")

    return _admin_email_common(request, recipients_qs, congress, event=None)


def _admin_email_common_thread(
    request, congress, subject, body, recipients, email_sender
):
    """we run a thread so we can return to the user straight away"""

    for recipient in recipients:
        context = {
            "name": recipient.first_name,
            "title1": f"Message from {request.user.full_name} on behalf of {congress}",
            "title2": subject,
            "email_body": body,
            "host": COBALT_HOSTNAME,
        }

        html_msg = render_to_string("notifications/email_with_2_headings.html", context)

        email_sender.queue_email(
            recipient.email,
            subject,
            html_msg,
            recipient,
            reply_to=request.user.email,
            sender=request.user,
        )

    # send
    email_sender.send()


def _admin_email_common(request, recipients_qs, congress, event=None):
    """Common function for sending emails to entrants"""

    form = EmailForm(request.POST or None)

    all_recipients = []
    for recipient in recipients_qs:
        if recipient.player not in all_recipients:
            all_recipients.append(recipient.player)

    if request.method == "POST" and form.is_valid():
        subject = form.cleaned_data["subject"]
        body = form.cleaned_data["body"]

        recipients = [request.user] if "test" in request.POST else all_recipients

        # start thread

        email_sender = CobaltEmail()

        args = {
            "request": request,
            "congress": congress,
            "subject": subject,
            "body": body,
            "recipients": recipients,
            "email_sender": email_sender,
        }

        thread = Thread(target=_admin_email_common_thread, kwargs=args)
        thread.setDaemon(True)
        thread.start()

        if "test" in request.POST:
            messages.success(
                request,
                f"Test message queued to be sent to {request.user.email}",
                extra_tags="cobalt-message-success",
            )
        else:  # Send for real
            if len(recipients) == 1:
                msg = "Message queued"
            else:
                msg = "%s messages queued" % (len(recipients))
            messages.success(request, msg, extra_tags="cobalt-message-success")

            if event:
                EventLog(
                    event=event,
                    actor=request.user,
                    action="Sent email to all event entrants",
                ).save()

                log_event(
                    user=request.user.href,
                    severity="INFO",
                    source="Events",
                    sub_source="events_admin",
                    message=f"Sent email to all entrants in {event.href}",
                )
            else:

                log_event(
                    user=request.user.href,
                    severity="INFO",
                    source="Events",
                    sub_source="events_admin",
                    message=f"Sent email to whole congress {congress.href}",
                )

            return redirect(
                "notifications:watch_emails", batch_id=email_sender.batch_id
            )

    # Screen will timeout if too many recipients - only really an issue for testing
    if len(all_recipients) > 1000:
        all_recipients = ["Too many to show"]

    return render(
        request,
        "events/admin_email.html",
        {
            "form": form,
            "congress": congress,
            "event": event,
            "count": len(all_recipients),
            "recipients": all_recipients,
        },
    )


@login_required()
def admin_bulletins(request, congress_id):
    """Manage bulletins"""

    congress = get_object_or_404(Congress, pk=congress_id)

    # check access
    role = "events.org.%s.edit" % congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if request.method == "POST":
        form = BulletinForm(request.POST, request.FILES)

        if form.is_valid():
            form.save()

            log_event(
                user=request.user.href,
                severity="INFO",
                source="Events",
                sub_source="events_admin",
                message=f"Added bulletin to {congress.href}",
            )

            messages.success(
                request, "Bulletin uploaded", extra_tags="cobalt-message-success"
            )

    else:
        form = BulletinForm()

    # Get bulletins
    bulletins = Bulletin.objects.filter(congress=congress).order_by("-pk")

    return render(
        request,
        "events/admin_bulletins.html",
        {"form": form, "congress": congress, "bulletins": bulletins},
    )


@login_required()
def admin_latest_news(request, congress_id):
    """Manage latest news section"""

    congress = get_object_or_404(Congress, pk=congress_id)

    # check access
    role = "events.org.%s.edit" % congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if request.method == "POST":
        form = LatestNewsForm(request.POST)

        if form.is_valid():
            congress.latest_news = form.cleaned_data["latest_news"]
            congress.save()
            messages.success(
                request, "Latest News Updated", extra_tags="cobalt-message-success"
            )

            log_event(
                user=request.user.href,
                severity="INFO",
                source="Events",
                sub_source="events_admin",
                message=f"Updated latest news for {congress.href}",
            )

            return redirect("events:view_congress", congress_id=congress.id)

    else:
        form = LatestNewsForm()

    return render(
        request,
        "events/admin_latest_news.html",
        {"form": form, "congress": congress},
    )


@login_required()
@transaction.atomic
def admin_move_entry(request, event_entry_id):
    """Move an entry to another event"""

    event_entry = get_object_or_404(EventEntry, pk=event_entry_id)

    congress = event_entry.event.congress

    # check access
    role = "events.org.%s.edit" % congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if request.method == "POST":
        new_event_id = request.POST.get("new_event_id")
        new_event = get_object_or_404(Event, pk=new_event_id)

        old_entry = copy.copy(event_entry.event)

        event_entry.event = new_event
        event_entry.save()

        # Log it

        EventLog(
            event=old_entry,
            event_entry=event_entry,
            actor=request.user,
            action=f"Moved entry to {new_event}",
        ).save()

        EventLog(
            event=event_entry.event,
            event_entry=event_entry,
            actor=request.user,
            action=f"Moved entry from {old_entry}",
        ).save()

        # Notify players

        for recipient in event_entry.evententryplayer_set.all():
            context = {
                "name": recipient.player.first_name,
                "title": "Entry moved to new event",
                "email_body": f"{request.user.full_name} has moved your entry to {event_entry.event}.<br><br>",
                "host": COBALT_HOSTNAME,
                "link": "/events/view",
                "link_text": "View Entry",
            }

            html_msg = render_to_string("notifications/email_with_button.html", context)

            # send
            contact_member(
                member=recipient.player,
                msg="Entry moved to new event",
                contact_type="Email",
                html_msg=html_msg,
                link="/events/view",
                subject="Entry moved to new event",
            )

        messages.success(request, "Entry Moved", extra_tags="cobalt-message-success")

        return redirect("events:admin_event_summary", event_id=event_entry.event.id)

    # Events we can move to, must be in this congress and same format
    events = (
        Event.objects.filter(congress=congress)
        .filter(player_format=event_entry.event.player_format)
        .exclude(id=event_entry.event.id)
    )

    return render(
        request,
        "events/admin_move_entry.html",
        {"events": events, "event_entry": event_entry},
    )


@login_required()
@transaction.atomic
def admin_event_entry_add(request, event_id):
    event = get_object_or_404(Event, pk=event_id)

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if request.method == "POST":

        # Get the players from the form
        players = []
        for count in range(6):
            player_id = request.POST.get(f"player_{count}", None)
            if player_id:
                player = get_object_or_404(User, pk=player_id)
                players.append(player)

        # create entry - make first entrant the primary_entrant
        event_entry = EventEntry()
        event_entry.event = event
        event_entry.primary_entrant = players[0]
        event_entry.notes = f"Entry added by convener {request.user.full_name}"

        # see if we got a category
        category = request.POST.get("category", None)
        if category:
            event_entry.category = get_object_or_404(Category, pk=category)

        event_entry.save()

        # Log it
        EventLog(
            event=event,
            actor=request.user,
            action=f"Event entry {event_entry.id} ({event_entry.primary_entrant}) created by convener",
            event_entry=event_entry,
        ).save()

        # create event entry players
        player_index = 0
        for player in players:
            event_entry_player = EventEntryPlayer()
            event_entry_player.event_entry = event_entry
            event_entry_player.player = player
            event_entry_player.payment_type = "TBA"
            entry_fee, discount, reason, description = event.entry_fee_for(
                event_entry_player.player
            )
            if player_index < 4:
                event_entry_player.entry_fee = entry_fee
                event_entry_player.reason = reason
            else:
                event_entry_player.entry_fee = 0
                event_entry_player.reason = "Team > 4"
                event_entry_player.payment_status = "Free"
            player_index += 1
            event_entry_player.save()

        # notify players
        for recipient in players:
            context = {
                "name": recipient.first_name,
                "title": "New convener entry",
                "email_body": f"{request.user.full_name} has entered you into {event}.<br><br>",
                "host": COBALT_HOSTNAME,
                "link": "/events/view",
                "link_text": "View Entry",
            }

            html_msg = render_to_string("notifications/email_with_button.html", context)

            # send
            contact_member(
                member=recipient,
                msg="New convener entry",
                contact_type="Email",
                html_msg=html_msg,
                link="/events/view",
                subject="New convener entry",
            )

            # Log it
            EventLog(
                event=event,
                actor=request.user,
                action=f"Player {recipient} added to entry: {event_entry.id} by convener",
                event_entry=event_entry,
            ).save()

        messages.success(request, "Entry Added", extra_tags="cobalt-message-success")

        return redirect("events:admin_evententry", evententry_id=event_entry.id)

    player_count_number = EVENT_PLAYER_FORMAT_SIZE[event.player_format]
    player_count = range(player_count_number)
    categories = Category.objects.filter(event=event)

    return render(
        request,
        "events/admin_event_entry_add.html",
        {
            "event": event,
            "player_count": player_count,
            "player_count_number": player_count_number,
            "categories": categories,
        },
    )


@login_required()
@transaction.atomic
def admin_event_entry_player_add(request, event_entry_id):
    """Add a player to a team"""

    event_entry = get_object_or_404(EventEntry, pk=event_entry_id)

    # check access
    role = "events.org.%s.edit" % event_entry.event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if event_entry.event.player_format != "Teams":
        messages.error(
            request,
            "Not a teams event - cannot add player",
            extra_tags="cobalt-message-error",
        )
        return redirect("events:admin_evententry", evententry_id=event_entry.id)

    tba = User.objects.get(pk=TBA_PLAYER)

    event_entry_player = EventEntryPlayer()
    event_entry_player.event_entry = event_entry
    event_entry_player.player = tba
    event_entry_player.payment_type = "TBA"
    event_entry_player.entry_fee = 0.0
    event_entry_player.save()

    # Log it
    EventLog(
        event=event_entry.event,
        actor=request.user,
        action=f"Player added to {event_entry.id} ({event_entry.primary_entrant}) created by convener",
        event_entry=event_entry,
    ).save()

    messages.success(request, "Player Added", extra_tags="cobalt-message-success")

    return redirect(
        "events:admin_evententryplayer", evententryplayer_id=event_entry_player.id
    )


@login_required()
@transaction.atomic
def admin_event_entry_player_delete(request, event_entry_player_id):
    """Delete a player from a team"""

    event_entry_player = get_object_or_404(EventEntryPlayer, pk=event_entry_player_id)
    event_entry = event_entry_player.event_entry

    # check access
    role = "events.org.%s.edit" % event_entry.event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if event_entry.event.player_format != "Teams":
        messages.error(
            request,
            "Not a teams event - cannot delete player",
            extra_tags="cobalt-message-error",
        )
        return redirect("events:admin_evententry", evententry_id=event_entry.id)

    if request.method == "POST":
        # Log it
        EventLog(
            event=event_entry.event,
            actor=request.user,
            action=f"Player {event_entry_player.player} deleted from {event_entry.id} ({event_entry.primary_entrant}) by convener",
            event_entry=event_entry,
        ).save()

        tba = User.objects.get(pk=TBA_PLAYER)
        event_entry_player.player = tba
        event_entry_player.save()

        messages.success(request, "Player Deleted", extra_tags="cobalt-message-success")

        return redirect("events:admin_evententry", evententry_id=event_entry.id)

    return render(
        request,
        "events/admin_event_entry_player_delete.html",
        {"event_entry_player": event_entry_player},
    )


@login_required()
@transaction.atomic
def admin_event_offsystem_pp_batch(request, event_id):
    """Handle Club PP system to allow clubs to use their existing PP system
    as a payment method. This handles batch work so upload a spreadsheet
    to the external PP system"""

    event = get_object_or_404(Event, pk=event_id)

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    # get players with pps
    event_entry_players = (
        EventEntryPlayer.objects.filter(event_entry__event=event)
        .filter(payment_type="off-system-pp")
        .exclude(event_entry__entry_status="Cancelled")
        .exclude(payment_status="Paid")
    )

    # calculate outstanding
    for event_entry_player in event_entry_players:
        event_entry_player.outstanding = (
            event_entry_player.entry_fee - event_entry_player.payment_received
        )

    event_entry_players_list = []
    for event_entry_player in event_entry_players:
        event_entry_players_list.append(
            (event_entry_player.id, event_entry_player.player.full_name)
        )

    if request.method == "POST":

        form = OffSystemPPForm(
            request.POST, event_entry_players=event_entry_players_list
        )
        if form.is_valid():

            # event_entry_players_list is the full list, event-entry_players_ids is
            # those that are selected

            event_entry_player_ids = form.cleaned_data["event_entry_players_list"]

            event_entry_players = EventEntryPlayer.objects.filter(
                id__in=event_entry_player_ids
            )

            if "export" in request.POST:  # CSV download

                local_dt = timezone.localtime(timezone.now(), TZ)
                today = dateformat.format(local_dt, "Y-m-d H:i:s")

                response = HttpResponse(content_type="text/csv")
                response[
                    "Content-Disposition"
                ] = 'attachment; filename="my-abf-to-pp.csv"'

                writer = csv.writer(response)
                writer.writerow(
                    [
                        "My ABF to PP Export",
                        "Downloaded by %s" % request.user.full_name,
                        today,
                    ]
                )
                writer.writerow(
                    [
                        f"{GLOBAL_ORG} No.",
                        "Name",
                        "Amount",
                    ]
                )

                for event_entry_player in event_entry_players:
                    writer.writerow(
                        [
                            event_entry_player.player.system_number,
                            event_entry_player.player.full_name,
                            event_entry_player.entry_fee
                            - event_entry_player.payment_received,
                        ]
                    )

                return response

            else:  # confirm payments

                for event_entry_player in event_entry_players:
                    outstanding = (
                        event_entry_player.entry_fee
                        - event_entry_player.payment_received
                    )
                    event_entry_player.payment_status = "Paid"
                    event_entry_player.payment_received = event_entry_player.entry_fee
                    event_entry_player.save()

                    event_entry_player.event_entry.check_if_paid()

                    EventLog(
                        event=event,
                        event_entry=event_entry_player.event_entry,
                        actor=request.user,
                        action=f"{event_entry_player.player} paid {outstanding} through off system PP",
                    ).save()

                length = event_entry_players.count()

                messages.success(
                    request,
                    f"Off System PP payments processed successfully. {length} players updated",
                    extra_tags="cobalt-message-success",
                )

                return redirect(
                    "events:admin_event_summary",
                    event_id=event.id,
                )
    else:
        form = OffSystemPPForm(event_entry_players=event_entry_players_list)

    return render(
        request,
        "events/admin_event_offsystem_pp_batch.html",
        {"event_entry_players": event_entry_players, "form": form, "event": event},
    )


@login_required()
def player_events_list(request, member_id, congress_id):
    """List what events a player has entered"""

    congress = get_object_or_404(Congress, pk=congress_id)

    # check access
    role = "events.org.%s.edit" % congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    player = get_object_or_404(User, pk=member_id)

    event_entry_players = EventEntryPlayer.objects.filter(
        event_entry__event__congress=congress
    ).filter(player=player)

    # Add partners onto the list
    for event_entry_player in event_entry_players:
        partners = EventEntryPlayer.objects.filter(
            event_entry=event_entry_player.event_entry
        )

        # Put the player first in the list
        txt = f"{event_entry_player.player.full_name}, "

        for partner in partners:
            if partner != event_entry_player:
                txt += f"{partner.player.full_name}, "

        # remove trailing comma and space
        event_entry_player.partners = txt[:-2]

    # Get log events
    events_entries_list = event_entry_players.values("event_entry")
    event_logs = EventLog.objects.filter(event_entry__in=events_entries_list)

    return render(
        request,
        "events/admin_player_events_list.html",
        {
            "player": player,
            "congress": congress,
            "event_entry_players": event_entry_players,
            "event_logs": event_logs,
        },
    )
