""" The file has the code relating to a convener managing an existing event """

import csv
from itertools import chain
from threading import Thread

import bleach
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.forms import formset_factory
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone, dateformat
from django.db.models import Sum, Q

from events.events_views.core import sort_events_by_start_date
from notifications.models import BlockNotification
from notifications.notifications_views.core import (
    contact_member,
    send_cobalt_email_with_template,
    create_rbac_batch_id,
)
from logs.views import log_event
from django.db import transaction, connection

from utils.views import download_csv
from events.models import (
    Congress,
    Category,
    Event,
    EventEntry,
    EventEntryPlayer,
    EVENT_PLAYER_FORMAT_SIZE,
    EventLog,
    EventPlayerDiscount,
    Bulletin,
    BasketItem,
)
from accounts.models import User
import requests
from events.forms import (
    EventEntryPlayerForm,
    RefundForm,
    EventPlayerDiscountForm,
    EmailForm,
    BulletinForm,
    LatestNewsForm,
    OffSystemPPForm,
    EventEntryPlayerTBAForm,
)
from rbac.views import rbac_user_has_role, rbac_forbidden
from payments.payments_views.core import (
    org_balance,
    update_account,
    update_organisation,
)
from django.contrib import messages
import copy
from cobalt.settings import (
    GLOBAL_ORG,
    BRIDGE_CREDITS,
    TIME_ZONE,
    COBALT_HOSTNAME,
    TBA_PLAYER,
    BLEACH_ALLOWED_TAGS,
    BLEACH_ALLOWED_ATTRIBUTES,
    BLEACH_ALLOWED_STYLES,
)
from utils.utils import cobalt_paginator
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

    # add start date and sort by start date
    events_list_sorted = sort_events_by_start_date(events)

    return render(
        request,
        "events/congress_admin/summary.html",
        {"events": events_list_sorted, "total": total, "congress": congress},
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
        "events/congress_admin/event_summary.html",
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
    ).order_by("first_created_date")

    has_categories = Category.objects.filter(event=event).exists()

    event_logs = EventLog.objects.filter(event_entry=event_entry).order_by("-id")

    return render(
        request,
        "events/congress_admin/event_entry.html",
        {
            "event_entry": event_entry,
            "event": event,
            "congress": congress,
            "event_entry_players": event_entry_players,
            "event_logs": event_logs,
            "has_categories": has_categories,
        },
    )


@login_required()
def admin_evententryplayer(request, evententryplayer_id):
    """Admin Event Entry Player View"""

    event_entry_player = get_object_or_404(EventEntryPlayer, pk=evententryplayer_id)

    old_entry = copy.copy(event_entry_player)
    event = event_entry_player.event_entry.event

    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if request.method == "POST":
        form = EventEntryPlayerForm(request.POST, instance=event_entry_player)
        if form.is_valid():
            form.save()

            # check if event entry payment status has changed
            event_entry_player.event_entry.check_if_paid()

            # Delete from players basket if present
            BasketItem.objects.filter(
                event_entry=event_entry_player.event_entry
            ).delete()

            messages.success(
                request, "Entry updated", extra_tags="cobalt-message-success"
            )

            # Log it
            for changed in form.changed_data:
                old_value = getattr(old_entry, changed)
                new_value = getattr(event_entry_player, changed)
                action = f"Convener Action: Changed {changed} from {old_value} to {new_value} on Entry:{old_entry.id} - {event_entry_player.event_entry}"
                log_action = f"Convener Action: Changed {changed} from {old_value} to {new_value} on Entry:{event_entry_player.event_entry.href}"

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

            return redirect(
                "events:admin_evententry",
                evententry_id=event_entry_player.event_entry.id,
            )
        else:
            print(form.errors)
    else:
        form = EventEntryPlayerForm(instance=event_entry_player)

    tba_form = EventEntryPlayerTBAForm(instance=event_entry_player)

    return render(
        request,
        "events/congress_admin/event_entry_player.html",
        {"event_entry_player": event_entry_player, "form": form, "tba_form": tba_form},
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
    entries.prefetch_related("evententryplayer_set")

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

    if event.allow_team_names:
        header = ["Team Name"] + header
    writer.writerow(header)

    for row in entries:

        players = ""
        received = Decimal(0)
        entry_fee = Decimal(0)

        for player in row.evententryplayer_set.order_by("pk").all():
            if player.player.id == TBA_PLAYER and player.override_tba_name:
                players += (
                    player.override_tba_name + "(manually set by administrator) - "
                )
            else:
                players += player.player.full_name + " - "
            try:
                received += player.payment_received
            except TypeError:
                pass  # ignore if payment_received is None
            entry_fee += player.entry_fee

        # remove trailing " - "
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

        if event.allow_team_names:
            this_row = [row.get_team_name()] + this_row

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

            # Use the override name if this is TBA and name is set
            if row.player.id == TBA_PLAYER and row.override_tba_name:
                names = row.override_tba_name.split(" ")
                if len(names) > 1:
                    player_first_name = names[0]
                    player_last_name = " ".join(names[1:])
                else:
                    player_first_name = row.override_tba_name
                    player_last_name = ""
                player_last_name = f"{player_last_name}(manually set by administrator)"
            else:
                player_first_name = row.player.first_name
                player_last_name = row.player.last_name

            writer.writerow(
                [
                    entry.primary_entrant,
                    row.player,
                    player_first_name,
                    player_last_name,
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

    # get details
    entries = event.evententry_set.exclude(entry_status="Cancelled").order_by(
        "first_created_date"
    )
    entries.select_related("event_entry_player")

    print(entries.query)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f"attachment; filename={event} - Scoring.csv"

    writer = csv.writer(response)

    _csv_event_writer(writer, entries, event)

    # Log it
    EventLog(
        event=event, actor=request.user, action=f"CSV Download of scoring for {event}"
    ).save()

    return response


@login_required()
def admin_congress_csv_scoring(request, congress_id):
    """Download a CSV file with info to import to a scoring program. For whole congress"""

    congress = get_object_or_404(Congress, pk=congress_id)

    role = "events.org.%s.edit" % congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f"attachment; filename={congress} - Scoring.csv"

    writer = csv.writer(response)

    events = Event.objects.filter(congress=congress)
    events.prefetch_related("evententry_set")

    for event in events:
        writer.writerow(
            [
                event,
            ]
        )
        entries = event.evententry_set.exclude(entry_status="Cancelled").order_by(
            "first_created_date"
        )
        _csv_event_writer(writer, entries, event)

    # Log it
    EventLog(
        event=event,
        actor=request.user,
        action=f"CSV Download of scoring for whole congress. {congress}",
    ).save()

    return response


def _csv_event_writer(writer, entries, event):
    """sub task to create event listing for CSV output"""

    title = "Pair No" if event.player_format == "Pairs" else "Team No"
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

    for count, entry in enumerate(entries, start=1):
        entry_line = 1
        team_name = entry.get_team_name()
        for row in entry.evententryplayer_set.order_by("-player").all():

            # Handle overriding the TBA details
            if row.player.id == TBA_PLAYER and row.override_tba_name:
                player_name = row.override_tba_name
                player_no = row.override_tba_system_number
                player_email = ""
            else:
                player_name = row.player.full_name
                player_no = row.player.system_number
                player_email = row.player.email

            data_row = [
                count,
                player_name.upper(),
                player_no,
                row.player.mobile,
                player_email,
                team_name,
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
            for _ in range(7 - entry_line):
                writer.writerow([count, "", "", "", "", team_name])


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
        "events/congress_admin/event_offsystem.html",
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
        "events/congress_admin/event_offsystem_pp.html",
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
        "events/congress_admin/event_unpaid.html",
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
        "events/congress_admin/players_report.html",
        {"event": event, "players": players},
    )


def get_player_mp_stats(player):
    """
    Get summary data
    """

    qry = "%s/mps/%s" % (
        GLOBAL_MPSERVER,
        player.system_number,
    )
    try:
        r = requests.get(qry, timeout=5).json()
    except Exception as exc:
        print(exc)
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
        request,
        "events/congress_admin/event_log.html",
        {"event": event, "things": things},
    )


@login_required()
def admin_evententry_delete(request, evententry_id):
    """Delete an event entry"""

    event_entry = get_object_or_404(EventEntry, pk=evententry_id)

    # check access
    role = "events.org.%s.edit" % event_entry.event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if event_entry.entry_status == "Cancelled":
        return HttpResponse("Event is already cancelled")

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
                    # We don't want to email TBA though
                    is_tba = True
                else:
                    is_tba = False

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

                # send
                if not is_tba:
                    contact_member(
                        member=player,
                        msg="Entry to %s cancelled" % event_entry.event.event_name,
                        contact_type="Email",
                        html_msg=email_body,
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

        # Also remove from basket if still present
        BasketItem.objects.filter(event_entry=event_entry).delete()

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
        "events/congress_admin/event_entry_delete.html",
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
        "events/congress_admin/event_player_discount.html",
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
    all_recipients = (
        EventEntryPlayer.objects.filter(event_entry__event=event)
        .exclude(event_entry__entry_status="Cancelled")
        .values_list("player__first_name", "player__last_name", "player__email")
        .distinct()
    )

    return _admin_email_common(request, all_recipients, event.congress, event)


@login_required()
def admin_unpaid_email(request, event_id):
    """Email all entrants to an event who have not paid"""

    event = get_object_or_404(Event, pk=event_id)

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    # who will receive this

    # Real people
    all_recipients_real = (
        EventEntryPlayer.objects.filter(event_entry__event=event)
        .exclude(player_id=TBA_PLAYER)
        .exclude(payment_status="Paid")
        .exclude(payment_status="Free")
        .exclude(event_entry__entry_status="Cancelled")
        .values_list("player__first_name", "player__last_name", "player__email")
        .distinct()
    )

    # For TBAs get the primary entrant
    all_recipients_tba = (
        EventEntryPlayer.objects.filter(event_entry__event=event)
        .filter(player_id=TBA_PLAYER)
        .exclude(payment_status="Paid")
        .exclude(payment_status="Free")
        .exclude(event_entry__entry_status="Cancelled")
        .values_list(
            "event_entry__primary_entrant__first_name",
            "event_entry__primary_entrant__last_name",
            "event_entry__primary_entrant__email",
        )
        .distinct()
    )

    all_recipients = list(chain(all_recipients_real, all_recipients_tba))

    return _admin_email_common(request, all_recipients, event.congress, event)


@login_required()
def admin_congress_email(request, congress_id):
    """Email all entrants to an entire congress"""

    congress = get_object_or_404(Congress, pk=congress_id)

    # check access
    role = "events.org.%s.edit" % congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    # who will receive this
    all_recipients = (
        EventEntryPlayer.objects.filter(event_entry__event__congress=congress)
        .exclude(event_entry__entry_status="Cancelled")
        .values_list("player__first_name", "player__last_name", "player__email")
        .distinct()
    )

    return _admin_email_common(request, all_recipients, congress, event=None)


def _admin_email_common_thread(request, congress, subject, body, recipients, batch_id):
    """we run a thread so we can return to the user straight away.
    Probably not necessary now we have Django Post Office"""

    # For some old congresses, contact_email was not required. Should be able to remove this in the future
    reply_to = congress.contact_email or request.user.email

    for recipient in recipients:

        context = {
            "name": recipient[0],
            "title1": f"Message from {request.user.full_name} on behalf of {congress}",
            "title2": subject,
            "email_body": body,
            "subject": subject,
        }

        send_cobalt_email_with_template(
            to_address=recipient[2],
            context=context,
            template="system - two headings",
            reply_to=reply_to,
            batch_id=batch_id,
        )

    # Django creates a new database connection for this thread so close it
    connection.close()


def _admin_email_common(request, all_recipients, congress, event=None):
    """Common function for sending emails to entrants"""

    form = EmailForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        subject = form.cleaned_data["subject"]
        body = form.cleaned_data["body"]

        body = bleach.clean(
            body,
            strip=True,
            tags=BLEACH_ALLOWED_TAGS,
            attributes=BLEACH_ALLOWED_ATTRIBUTES,
            styles=BLEACH_ALLOWED_STYLES,
        )

        recipients = (
            [(request.user.first_name, request.user.last_name, request.user.email)]
            if "test" in request.POST
            else all_recipients
        )

        batch_id = create_rbac_batch_id(
            f"events.org.{congress.congress_master.org.id}.view"
        )

        # start thread
        args = {
            "request": request,
            "congress": congress,
            "subject": subject,
            "body": body,
            "recipients": recipients,
            "batch_id": batch_id,
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

            return redirect("notifications:watch_emails", batch_id=batch_id)

    recipient_count = len(all_recipients)

    # Screen will timeout if too many recipients - only really an issue for testing
    if len(all_recipients) > 1000:
        all_recipients = ["Too many to show"]

    return render(
        request,
        "events/congress_admin/email.html",
        {
            "form": form,
            "congress": congress,
            "event": event,
            "count": recipient_count,
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
        "events/congress_admin/bulletins.html",
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
        "events/congress_admin/latest_news.html",
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

            # send
            contact_member(
                member=recipient.player,
                msg="Entry moved to new event",
                contact_type="Email",
                html_msg=f"{request.user.full_name} has moved your entry to {event_entry.event}.<br><br>",
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
        "events/congress_admin/move_entry.html",
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

            # send
            contact_member(
                member=recipient,
                msg="New convener entry",
                contact_type="Email",
                html_msg=f"{request.user.full_name} has entered you into {event}.<br><br>",
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
        "events/congress_admin/event_entry_add.html",
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

        # Delete if payment_type is free (5th or 6th player) otherwise change to TBA

        if event_entry_player.payment_type == "Free":
            event_entry_player.delete()
            messages.success(
                request, "Player Deleted", extra_tags="cobalt-message-success"
            )
        else:

            contact_member(
                member=event_entry_player.player,
                msg="Convener removed you from team",
                contact_type="Email",
                html_msg=f"{request.user.full_name} has removed you from a team entry to {event_entry.event}.<br><br>",
                link="/events/view",
                subject="Removed from team by Convener",
            )

            tba = User.objects.get(pk=TBA_PLAYER)
            event_entry_player.player = tba
            event_entry_player.save()

            messages.success(
                request,
                "Player payment type is not Free so changed player to TBA. To Delete player first set payment type to Free.",
                extra_tags="cobalt-message-success",
            )

        return redirect("events:admin_evententry", evententry_id=event_entry.id)

    return render(
        request,
        "events/congress_admin/event_entry_player_delete.html",
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

                    # Delete from players basket if present
                    BasketItem.objects.filter(
                        event_entry=event_entry_player.event_entry
                    ).delete()

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
        "events/congress_admin/event_offsystem_pp_batch.html",
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
        "events/congress_admin/player_events_list.html",
        {
            "player": player,
            "congress": congress,
            "event_entry_players": event_entry_players,
            "event_logs": event_logs,
        },
    )


@login_required()
def admin_event_payment_methods(request, event_id):
    """List of payment methods including Cancelled entries"""

    event = get_object_or_404(Event, pk=event_id)

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    event_entry_players = EventEntryPlayer.objects.filter(event_entry__event=event)

    # Get log events
    event_logs = EventLog.objects.filter(event=event)

    return render(
        request,
        "events/congress_admin/event_payment_methods.html",
        {
            "event": event,
            "event_entry_players": event_entry_players,
            "event_logs": event_logs,
        },
    )


@login_required()
def admin_event_payment_methods_csv(request, event_id):
    """List of payment methods including Cancelled entries as csv"""

    event = get_object_or_404(Event, pk=event_id)

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    event_entry_players = EventEntryPlayer.objects.filter(event_entry__event=event)

    return download_csv(request, event_entry_players)


@login_required()
def admin_event_entry_change_category_htmx(request):
    """Allow admins to change categories for entries in an event that has categories defined"""

    event_id = request.POST.get("event_id")
    event = get_object_or_404(Event, pk=event_id)
    event_entry_id = request.POST.get("event_entry_id")
    event_entry = get_object_or_404(EventEntry, pk=event_entry_id)

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if "update" in request.POST:
        new_category_id = request.POST.get("category")
        new_category = get_object_or_404(Category, pk=new_category_id)
        event_entry.category = new_category
        event_entry.save()

        EventLog(
            event=event,
            event_entry=event_entry,
            actor=request.user,
            action=f"Administrator changed category to {new_category}",
        ).save()

        return render(
            request,
            "events/congress_admin/admin_event_entry_category_htmx.html",
            {"event": event, "event_entry": event_entry},
        )

    categories = Category.objects.filter(event=event)

    return render(
        request,
        "events/congress_admin/admin_event_entry_change_category_htmx.html",
        {"event": event, "event_entry": event_entry, "categories": categories},
    )


@login_required()
def convener_settings(request, congress_id):
    """Allow conveners to manage their personal settings for congresses"""

    congress = get_object_or_404(Congress, pk=congress_id)

    # check access
    role = "events.org.%s.edit" % congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    # We change settings through a GET so see if we need to do anything
    if request.method == "GET":

        # Everything
        if request.GET.get("all_off") == "True":
            # Turn off all and delete anything else
            BlockNotification.objects.filter(member=request.user).delete()
            BlockNotification(
                member=request.user,
                identifier=BlockNotification.Identifier.CONVENER_EMAIL_BY_EVENT,
                model_id=None,
            ).save()
            print("Turn all_off true")

        if request.GET.get("all_off") == "False":
            # Turn on all
            BlockNotification.objects.filter(
                member=request.user,
            ).delete()
            print("Turn all_off false")

        # This org
        if request.GET.get("this_org_off") == "True":
            # Turn off org and delete anything else
            BlockNotification.objects.filter(
                member=request.user,
                identifier=BlockNotification.Identifier.CONVENER_EMAIL_BY_EVENT,
            ).delete()
            BlockNotification(
                member=request.user,
                identifier=BlockNotification.Identifier.CONVENER_EMAIL_BY_ORG,
                model_id=congress.congress_master.org.id,
            ).save()
            print("Turn this_org_off true")

        if request.GET.get("this_org_off") == "False":
            # Turn on org
            BlockNotification.objects.filter(
                member=request.user,
                identifier=BlockNotification.Identifier.CONVENER_EMAIL_BY_ORG,
                model_id=congress.congress_master.org.id,
            ).delete()
            print("Turn this_org_off false")

        if request.GET.get("this_congress_off") == "True":
            # Turn off congress and delete anything else
            # BlockNotification.objects.filter(member=request.user).delete()
            BlockNotification(
                member=request.user,
                identifier=BlockNotification.Identifier.CONVENER_EMAIL_BY_EVENT,
                model_id=congress.id,
            ).save()
            print("Turn this_congress_off true")

        if request.GET.get("this_congress_off") == "False":
            # Turn on congress
            BlockNotification.objects.filter(
                member=request.user,
                identifier=BlockNotification.Identifier.CONVENER_EMAIL_BY_EVENT,
                model_id=congress.id,
            ).delete()
            print("Turn this_congress_off false")

    # Build current state for view
    this_congress_off = BlockNotification.objects.filter(
        member=request.user,
        identifier=BlockNotification.Identifier.CONVENER_EMAIL_BY_EVENT,
        model_id=congress.id,
    ).exists()
    this_org_off = BlockNotification.objects.filter(
        member=request.user,
        identifier=BlockNotification.Identifier.CONVENER_EMAIL_BY_ORG,
        model_id=congress.congress_master.org.id,
    ).exists()
    all_off = BlockNotification.objects.filter(
        member=request.user,
        identifier=BlockNotification.Identifier.CONVENER_EMAIL_BY_EVENT,
        model_id=None,
    ).exists()

    return render(
        request,
        "events/congress_admin/convener_settings.html",
        {
            "congress": congress,
            "this_congress_off": this_congress_off,
            "this_org_off": this_org_off,
            "all_off": all_off,
        },
    )


@login_required()
def edit_team_name_htmx(request):
    """HTMX snippet to edit the team name"""

    event_entry = get_object_or_404(EventEntry, pk=request.POST.get("event_entry_id"))

    # check access
    role = "events.org.%s.edit" % event_entry.event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if "cancel" in request.POST:
        return render(
            request,
            "events/congress_admin/event_entry_team_name_htmx.html",
            {"event_entry": event_entry},
        )

    if "save" in request.POST:
        team_name = request.POST.get("team_name")
        event_entry.team_name = team_name
        event_entry.save()
        EventLog(
            event=event_entry.event,
            event_entry=event_entry,
            actor=request.user,
            action=f"Admin changed team name to '{team_name}'",
        ).save()
        return render(
            request,
            "events/congress_admin/event_entry_team_name_htmx.html",
            {"event_entry": event_entry},
        )

    return render(
        request,
        "events/congress_admin/event_entry_team_name_edit_htmx.html",
        {"event_entry": event_entry},
    )


@login_required()
def edit_player_name_htmx(request):
    """HTMX snippet to edit the player name on an EventEntryPlayer"""

    event_entry_player = get_object_or_404(
        EventEntryPlayer, pk=request.POST.get("event_entry_player_id")
    )
    event = event_entry_player.event_entry.event

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    old_user = copy.copy(event_entry_player.player)
    new_user = get_object_or_404(User, pk=request.POST.get("player_id"))
    event_entry_player.player = new_user
    # replace any TBA data
    event_entry_player.override_tba_name = None
    event_entry_player.override_tba_system_number = 0
    event_entry_player.save()
    message = "User changed"

    # notify deleted member
    if old_user.id != TBA_PLAYER:

        # send
        contact_member(
            member=old_user,
            msg=f"Removed from - {event}",
            contact_type="Email",
            html_msg=f"The convener, {request.user.full_name}, has removed you from this event.<br><br>",
            link="/events/view",
            subject=f"Removed from - {event}",
        )

    # notify added member
    if new_user.id != TBA_PLAYER:

        # send
        contact_member(
            member=new_user,
            msg="Added to - %s" % event,
            contact_type="Email",
            html_msg=f"The convener, {request.user.full_name}, has added you to this event.<br><br>",
            link="/events/view",
            subject="Added to - %s" % event,
        )

        EventLog(
            event=event,
            event_entry=event_entry_player.event_entry,
            actor=request.user,
            action=f"Convener Action: Changed player from {old_user} to {new_user} on Entry:{event_entry_player.event_entry.href}",
        ).save()

    tba_form = EventEntryPlayerTBAForm(instance=event_entry_player)

    return render(
        request,
        "events/congress_admin/event_entry_player_name_htmx.html",
        {
            "event_entry_player": event_entry_player,
            "tba_form": tba_form,
            "message": message,
        },
    )


@login_required()
def edit_tba_player_details_htmx(request):
    """Override the name and ABF number of a TBA player"""

    event_entry_player = get_object_or_404(
        EventEntryPlayer, pk=request.POST.get("event_entry_player_id")
    )
    event = event_entry_player.event_entry.event

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    tba_form = EventEntryPlayerTBAForm(request.POST, instance=event_entry_player)

    message = ""

    if tba_form.is_valid():
        tba_form.save()
        message = "Data saved"

    return render(
        request,
        "events/congress_admin/event_entry_player_name_htmx.html",
        {
            "event_entry_player": event_entry_player,
            "tba_form": tba_form,
            "message": message,
        },
    )
