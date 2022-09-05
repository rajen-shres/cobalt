import csv
import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404

from club_sessions.club_sessions_views.decorators import user_is_club_director
from club_sessions.club_sessions_views.sessions import load_session_entry_static
from club_sessions.models import Session, SessionEntry
from cobalt.settings import GLOBAL_ORG
from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden
from utils.views import download_csv


def _build_empty_report_data_structure(session_fees):
    """Build the empty data structure for the report table"""

    summary_table = {}

    # Now build the other rows
    for membership_type in session_fees:

        summary_table[membership_type] = {}

        for payment_method in session_fees[membership_type]:
            summary_table[membership_type][payment_method] = {}
            # Handle membership and payment eg. Guest Cash
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
        if session_entry.system_number not in [1, -1]:
            membership_type = membership_type_dict.get(
                session_entry.system_number, "Guest"
            )
            payment_method = session_entry.payment_method.payment_method

            # This cell
            summary_table[membership_type][payment_method][
                "paid"
            ] += session_entry.amount_paid
            summary_table[membership_type][payment_method]["fee"] += session_entry.fee

            # Row totals
            summary_table[membership_type]["row_total"][
                "paid"
            ] += session_entry.amount_paid
            summary_table[membership_type]["row_total"]["fee"] += session_entry.fee

            # Column totals
            summary_table["Totals"][payment_method]["paid"] += session_entry.amount_paid
            summary_table["Totals"][payment_method]["fee"] += session_entry.fee

            # Grand total
            summary_table["Totals"]["row_total"]["paid"] += session_entry.amount_paid
            summary_table["Totals"]["row_total"]["fee"] += session_entry.fee

    return summary_table


def _mark_rows_with_data_in_report_data_structure(summary_table):
    """We want to show if a row has data or not to remove clutter (blank rows)"""

    row_has_data = {}

    for membership_type in summary_table:
        row_has_data[membership_type] = False
        for payment_method in summary_table[membership_type]:

            if (
                summary_table[membership_type][payment_method]["fee"] != 0
                or summary_table[membership_type][payment_method]["paid"] != 0
            ):
                row_has_data[membership_type] = True

    return row_has_data


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
    column_headings = list(session_fees["Guest"])

    # Build summary around session_fees - start by building structure
    summary_table = _build_empty_report_data_structure(session_fees)

    # Add the session data in
    summary_table = _add_data_to_report_data_structure(
        summary_table, session_entries, membership_type_dict
    )

    # Go through and mark which rows/columns have data
    row_has_data = _mark_rows_with_data_in_report_data_structure(summary_table)
    column_has_data = _mark_columns_with_data_in_report_data_structure(summary_table)

    # See if user wants to see nothing in the report
    show_blanks = bool(request.POST.get("show_blanks", False))

    return render(
        request,
        "club_sessions/reports/reconciliation.html",
        {
            "club": club,
            "session": session,
            "session_entries": session_entries,
            "summary_table": summary_table,
            "column_headings": column_headings,
            "row_has_data": row_has_data,
            "column_has_data": column_has_data,
            "show_blanks": show_blanks,
        },
    )


@login_required()
def csv_download(request, session_id):
    """Download CSV of player details from a session"""

    session = get_object_or_404(Session, pk=session_id)
    club = session.session_type.organisation

    # Check access
    club_role = f"club_sessions.sessions.{club.id}.edit"
    if not rbac_user_has_role(request.user, club_role):
        return rbac_forbidden(request, club_role)

    # Get session_entries
    session_entries = SessionEntry.objects.filter(session=session)

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
        f"{GLOBAL_ORG} Number",
        "Pair Team Number",
        "Seat",
        "Payment Method",
        "Fee",
        "Amount Paid",
    ]
    writer.writerow(field_names)
    # Write data rows
    for session_entry in session_entries:
        values = [
            session.description,
            session.session_date,
            session_entry.system_number,
            session_entry.pair_team_number,
            session_entry.seat,
            session_entry.payment_method,
            session_entry.fee,
            session_entry.amount_paid,
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
