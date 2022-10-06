import csv
import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404

from accounts.models import User
from club_sessions.views.core import (
    PLAYING_DIRECTOR,
    SITOUT,
    VISITOR,
    load_session_entry_static,
)
from club_sessions.views.decorators import user_is_club_director
from club_sessions.models import Session, SessionEntry, SessionMiscPayment
from cobalt.settings import GLOBAL_ORG
from payments.models import MemberTransaction
from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden


def _build_empty_report_data_structure(session_fees):
    """Build the empty data structure for the report table"""

    summary_table = {}

    # Now build the other rows
    for membership_type in session_fees:

        summary_table[membership_type] = {}

        for payment_method in session_fees[membership_type]:
            summary_table[membership_type][payment_method] = {}
            # Handle membership and payment e.g. Guest Cash
            summary_table[membership_type][payment_method][
                "default_fee"
            ] = session_fees[membership_type][payment_method]
            summary_table[membership_type][payment_method]["fee"] = Decimal(0.0)
            summary_table[membership_type][payment_method]["paid"] = Decimal(0.0)

        # Also create a total for the row, e.g. total for Guests for all payment types
        summary_table[membership_type]["row_total"] = {}
        summary_table[membership_type]["row_total"]["fee"] = Decimal(0.0)
        summary_table[membership_type]["row_total"]["paid"] = Decimal(0.0)

    # Add totals at the bottom - again use Guest as our reference row
    summary_table["Totals"] = {}
    for payment_method in session_fees["Guest"]:
        summary_table["Totals"][payment_method] = {}
        summary_table["Totals"][payment_method]["fee"] = Decimal(0.0)
        summary_table["Totals"][payment_method]["paid"] = Decimal(0.0)

    # Grand totals
    summary_table["Totals"]["row_total"] = {}
    summary_table["Totals"]["row_total"]["paid"] = Decimal(0.0)
    summary_table["Totals"]["row_total"]["fee"] = Decimal(0.0)

    return summary_table


def _add_data_to_report_data_structure(
    summary_table, session_entries, membership_type_dict
):
    """Add in the data to the empty summary_table from the session_entries"""

    for session_entry in session_entries:

        # Skip sit outs and directors
        if session_entry.system_number not in [PLAYING_DIRECTOR, SITOUT]:
            membership_type = membership_type_dict.get(
                session_entry.system_number, "Guest"
            )
            payment_method = session_entry.payment_method.payment_method

            # This cell
            if session_entry.is_paid:
                summary_table[membership_type][payment_method][
                    "paid"
                ] += session_entry.fee
            summary_table[membership_type][payment_method]["fee"] += session_entry.fee

            # Row totals
            if session_entry.is_paid:
                summary_table[membership_type]["row_total"]["paid"] += session_entry.fee
            summary_table[membership_type]["row_total"]["fee"] += session_entry.fee

            # Column totals
            if session_entry.is_paid:
                summary_table["Totals"][payment_method]["paid"] += session_entry.fee
            summary_table["Totals"][payment_method]["fee"] += session_entry.fee

            # Grand total
            if session_entry.is_paid:
                summary_table["Totals"]["row_total"]["paid"] += session_entry.fee
            summary_table["Totals"]["row_total"]["fee"] += session_entry.fee

    return summary_table


def _mark_rows_with_data_in_report_data_structure(summary_table):
    """We want to show if a row has data or not to remove clutter (blank rows)"""

    # Does this table have any data?
    any_data = False

    row_has_data = {}

    for membership_type in summary_table:
        row_has_data[membership_type] = False
        for payment_method in summary_table[membership_type]:

            if (
                summary_table[membership_type][payment_method]["fee"] != 0
                or summary_table[membership_type][payment_method]["paid"] != 0
            ):
                row_has_data[membership_type] = True
                any_data = True

    return any_data, row_has_data


def _mark_columns_with_data_in_report_data_structure(summary_table):
    """We want to show if a column has data or not to remove clutter (blank payment type columns)"""

    column_has_data = {}

    # Go through data
    for membership_type in summary_table:
        for payment_method in summary_table[membership_type]:

            # Add key if not set yet
            if payment_method not in column_has_data:
                column_has_data[payment_method] = False

            # If we have data already, move on
            if column_has_data[payment_method]:
                continue

            # Check for data
            if (
                summary_table[membership_type][payment_method]["fee"] != 0
                or summary_table[membership_type][payment_method]["paid"] != 0
            ):
                column_has_data[payment_method] = True

    return column_has_data


@user_is_club_director()
def reconciliation_htmx(request, club, session):
    """Basic report of a session"""

    # Load starting data
    (
        session_entries,
        mixed_dict,
        session_fees,
        membership_type_dict,
    ) = load_session_entry_static(session, club)

    # We want the column names so use the Guest row which is always present
    # This will give us e.g. ['Bank Transfer', 'Bridge Credits', 'Cash', 'IOU']
    column_headings = sorted(session_fees["Guest"])

    # Build summary around session_fees - start by building structure
    summary_table = _build_empty_report_data_structure(session_fees)

    # Add the session data in
    summary_table = _add_data_to_report_data_structure(
        summary_table, session_entries, membership_type_dict
    )

    # Go through and mark which rows/columns have data
    _, row_has_data = _mark_rows_with_data_in_report_data_structure(summary_table)
    column_has_data = _mark_columns_with_data_in_report_data_structure(summary_table)

    # We need to sort the entries in the summary table by payment method, the same as the headers
    new_table = {}
    for row in summary_table:
        new_row = dict(sorted(summary_table[row].items()))
        new_table[row] = new_row
    summary_table = new_table

    # See if user wants to see blank stuff in the report
    show_blanks = bool(request.POST.get("show_blanks", False))

    (
        extras_summary_table,
        extras_any_data,
        extras_row_has_data,
        extras_column_has_data,
    ) = _reconciliation_extras(session, column_headings)

    return render(
        request,
        "club_sessions/reports/reconciliation.html",
        {
            "club": club,
            "session": session,
            "column_headings": column_headings,
            "summary_table": summary_table,
            "row_has_data": row_has_data,
            "column_has_data": column_has_data,
            "extras_summary_table": extras_summary_table,
            "extras_row_has_data": extras_row_has_data,
            "extras_column_has_data": extras_column_has_data,
            "extras_any_data": extras_any_data,
            "show_blanks": show_blanks,
        },
    )


def _reconciliation_extras(session, column_headings):
    """Get summarised view of extras for a session

    We use the same column headings as the session fees table - payment types

    For the rows we use the description

    """

    extras_summary_table = {}

    # Get data
    extras = (
        SessionMiscPayment.objects.filter(session_entry__session=session)
        .order_by("description", "payment_method__payment_method")
        .select_related("payment_method")
    )

    # Build table structure first
    for extra in extras:
        if extra.description not in extras_summary_table:
            extras_summary_table[extra.description] = {}
            for column_heading in column_headings:
                extras_summary_table[extra.description][column_heading] = {
                    "fee": Decimal(0),
                    "paid": Decimal(0),
                }

            # Also create a total for the row, e.g. total for Coffee for all payment types
            extras_summary_table[extra.description]["row_total"] = {
                "fee": Decimal(0),
                "paid": Decimal(0),
            }

    # Add totals at the bottom
    extras_summary_table["Totals"] = {}
    for column_heading in column_headings:
        extras_summary_table["Totals"][column_heading] = {
            "fee": Decimal(0),
            "paid": Decimal(0),
        }

    # Grand totals
    extras_summary_table["Totals"]["row_total"] = {
        "fee": Decimal(0),
        "paid": Decimal(0),
    }

    # Now fill in data
    for extra in extras:
        extras_summary_table[extra.description][extra.payment_method.payment_method][
            "fee"
        ] += extra.amount
        if extra.payment_made:
            extras_summary_table[extra.description][
                extra.payment_method.payment_method
            ]["paid"] += extra.amount

        # Row totals
        if extra.payment_made:
            extras_summary_table[extra.description]["row_total"]["paid"] += extra.amount
        extras_summary_table[extra.description]["row_total"]["fee"] += extra.amount

        # Column totals
        if extra.payment_made:
            extras_summary_table["Totals"][extra.payment_method.payment_method][
                "paid"
            ] += extra.amount
        extras_summary_table["Totals"][extra.payment_method.payment_method][
            "fee"
        ] += extra.amount

        # Grand total
        if extra.payment_made:
            extras_summary_table["Totals"]["row_total"]["paid"] += extra.amount
        extras_summary_table["Totals"]["row_total"]["fee"] += extra.amount

    # Go through and mark which rows/columns have data
    any_data, extras_row_has_data = _mark_rows_with_data_in_report_data_structure(
        extras_summary_table
    )
    extras_column_has_data = _mark_columns_with_data_in_report_data_structure(
        extras_summary_table
    )

    return extras_summary_table, any_data, extras_row_has_data, extras_column_has_data


def _get_name_for_csv(session_entry, mixed_dict):
    """helper to get the name to use in the csv"""

    if session_entry.system_number == PLAYING_DIRECTOR:
        return "Playing Director"
    elif session_entry.system_number == SITOUT:
        return "Sitout"
    elif session_entry.system_number == VISITOR:
        return session_entry.player_name_from_file
    else:
        return mixed_dict.get(session_entry.system_number).get("value")


@login_required()
def csv_download(request, session_id):
    """Download CSV of player details from a session"""

    session = get_object_or_404(Session, pk=session_id)
    club = session.session_type.organisation

    # Check access
    club_role = f"club_sessions.sessions.{club.id}.edit"
    if not rbac_user_has_role(request.user, club_role):
        return rbac_forbidden(request, club_role)

    # Get dictionaries
    (
        session_entries,
        mixed_dict,
        session_fees,
        membership_type_dict,
    ) = load_session_entry_static(session, club)

    # Get extras
    extras = SessionMiscPayment.objects.filter(
        session_entry__session=session
    ).select_related("session_entry")

    # Create CSV
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{session}.csv"'

    # the csv writer
    writer = csv.writer(response)
    writer.writerow([club.name, f"Downloaded by {request.user.full_name}"])

    # Write a first row with header information
    field_names = [
        "Session",
        "Date",
        "Name",
        f"{GLOBAL_ORG} Number",
        "Pair Team Number",
        "Seat",
        "Payment Method",
        "Fee",
        "Paid",
    ]
    writer.writerow(field_names)
    # Write data rows
    for session_entry in session_entries:
        if session_entry.payment_method:
            payment_method = session_entry.payment_method.payment_method
        else:
            payment_method = ""

        values = [
            session.description,
            session.session_date,
            _get_name_for_csv(session_entry, mixed_dict),
            session_entry.system_number,
            session_entry.pair_team_number,
            session_entry.seat,
            payment_method,
            session_entry.fee,
            session_entry.is_paid,
        ]
        writer.writerow(values)

    # Extras
    if extras:
        writer.writerow([])
        writer.writerow(["Extras"])
        writer.writerow([])
        # Write a first row with header information
        field_names = [
            "Session",
            "Name",
            f"{GLOBAL_ORG} Number",
            "Description",
            "Payment Method",
            "Fee",
            "Paid",
        ]
        writer.writerow(field_names)

        # Write data rows
        for extra in extras:
            values = [
                extra.session_entry.session,
                _get_name_for_csv(extra.session_entry, mixed_dict),
                extra.session_entry.system_number,
                extra.description,
                extra.payment_method.payment_method,
                extra.amount,
                extra.payment_made,
            ]
            writer.writerow(values)

    return response


@user_is_club_director()
def import_messages_htmx(request, club, session):
    """Show the messages generated when we imported the file"""

    messages = json.loads(session.import_messages)

    return render(
        request,
        "club_sessions/reports/import_messages_htmx.html",
        {"messages": messages},
    )


@user_is_club_director()
def low_balance_report_htmx(request, club, session):
    """Show low balances for people in session"""

    # Get all system numbers
    player_system_numbers = (
        SessionEntry.objects.filter(session=session)
        .exclude(system_number__in=[PLAYING_DIRECTOR, SITOUT, VISITOR])
        .values_list("system_number", flat=True)
    )

    # Get last transaction for those players
    last_trans = (
        MemberTransaction.objects.filter(
            member__system_number__in=player_system_numbers
        )
        .order_by("member", "-pk")
        .distinct("member")
        .select_related("member")
    )

    # Get players without transactions
    players_with_transactions = last_trans.values("member_id")
    players_without_transactions = User.objects.filter(
        system_number__in=player_system_numbers
    ).exclude(id__in=players_with_transactions)

    return render(
        request,
        "club_sessions/reports/low_balance_htmx.html",
        {
            "last_trans": last_trans,
            "players_without_transactions": players_without_transactions,
        },
    )
