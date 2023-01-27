import csv
import json

import math
import xlsxwriter
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.utils.html import strip_tags

from accounts.models import User
from club_sessions.views.core import (
    PLAYING_DIRECTOR,
    SITOUT,
    VISITOR,
    load_session_entry_static,
)
from club_sessions.views.decorators import user_is_club_director
from club_sessions.models import Session, SessionEntry, SessionMiscPayment
from cobalt.settings import GLOBAL_ORG, COBALT_HOSTNAME, GLOBAL_TITLE
from cobalt.version import COBALT_VERSION
from payments.models import MemberTransaction, OrgPaymentMethod
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
            print(session_entry)
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

    We use the same column headings as the table fees table - payment types

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
        match = mixed_dict.get(session_entry.system_number)
        return (
            match.get("value").full_name
            if match
            else session_entry.player_name_from_file
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

    # Get dictionaries
    (
        session_entries,
        mixed_dict,
        session_fees,
        membership_type_dict,
    ) = load_session_entry_static(session, club)

    # Manipulate the data for the report
    for session_entry in session_entries:
        # Payment method
        if session_entry.payment_method:
            session_entry.payment_method_display = (
                session_entry.payment_method.payment_method
            )
        else:
            session_entry.payment_method_display = ""

        # Fudge the session entries for non-players to show as free if no payment taken
        if (
            session_entry.system_number in [PLAYING_DIRECTOR, SITOUT]
            and session_entry.fee == 0
        ):
            session_entry.payment_method_display = "Free"

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

    # basic session details
    writer.writerow([])
    if session.status == Session.SessionStatus.COMPLETE:
        writer.writerow(["Status", "Complete"])
    else:
        writer.writerow(["Status", "Incomplete"])
    writer.writerow(["Director", session.director])
    writer.writerow(["Description", session.description])
    writer.writerow(["Session Date", session.session_date])
    writer.writerow(["Session Type", session.session_type.name])
    writer.writerow(["Time of Day", session.time_of_day])
    if session.venue:
        writer.writerow(["Venue", session.venue])
    writer.writerow([])

    # notes if we have any
    if session.director_notes:
        writer.writerow(["Director Notes", session.director_notes])
        writer.writerow([])

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
        "Processed",
    ]
    writer.writerow(field_names)
    # Write data rows
    for session_entry in session_entries:

        # Payment status
        is_paid = "Yes" if session_entry.is_paid else "No"

        # Don't show values for free players
        if session_entry.payment_method_display == "Free":
            is_paid = ""
            session_entry.fee = ""

        values = [
            session.description,
            session.session_date,
            _get_name_for_csv(session_entry, mixed_dict),
            session_entry.system_number,
            session_entry.pair_team_number,
            session_entry.seat,
            session_entry.payment_method_display,
            session_entry.fee,
            is_paid,
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
            "Date",
            "Name",
            f"{GLOBAL_ORG} Number",
            "Description",
            "",
            "Payment Method",
            "Fee",
            "Processed",
        ]
        writer.writerow(field_names)

        # Write data rows
        for extra in extras:
            payment_made = "Yes" if extra.payment_made else "No"
            values = [
                extra.session_entry.session.description,
                session.session_date,
                _get_name_for_csv(extra.session_entry, mixed_dict),
                extra.session_entry.system_number,
                extra.description,
                "",
                extra.payment_method.payment_method,
                extra.amount,
                payment_made,
            ]
            writer.writerow(values)

    # Now do payment method summaries
    payment_methods, extras = payment_method_summary(session)

    writer.writerow([])
    writer.writerow(["Payment Methods Summary"])
    writer.writerow([])
    # Write a first row with header information
    field_names = [
        "Payment Method",
        "Players Paid",
        "Players Un-Paid",
        "Amount Paid",
        "Amount Un-Paid",
    ]
    writer.writerow(field_names)

    for payment_method in payment_methods:
        payment_method_display = payment_method or "Free"
        values = [
            payment_method_display,
            payment_methods[payment_method]["paid"]["count"],
            payment_methods[payment_method]["unpaid"]["count"],
            payment_methods[payment_method]["paid"]["total"],
            payment_methods[payment_method]["unpaid"]["total"],
        ]
        writer.writerow(values)

    if extras:
        writer.writerow([])
        writer.writerow(["Extras Summary"])
        writer.writerow([])
        # Write a first row with header information
        field_names = [
            "Payment Method",
            "Number Paid",
            "Number Un-Paid",
            "Amount Paid",
            "Amount Un-Paid",
        ]
        writer.writerow(field_names)

        for extra in extras:
            values = [
                extra,
                extras[extra]["paid"]["count"],
                extras[extra]["unpaid"]["count"],
                extras[extra]["paid"]["total"],
                extras[extra]["unpaid"]["total"],
            ]
            writer.writerow(values)

    return response


class XLSXFormat:
    """Holds common formatting for Excel download"""

    # Bootstrap / Creative Tim Colours
    bs_success = "#4CAF50"
    bs_primary = "#9C27B0"
    bs_danger = "#F44336"
    bs_info = "#00BCD4"
    bs_warning = "#FF9800"

    # Other colours
    bs_white = "#FFFFFF"
    bs_grey = "#D5FFFF"
    bs_dark_grey = "#ADCECE"

    h1 = {
        "bold": True,
        "font_size": 50,
        "center_across": True,
        "bg_color": bs_primary,
        "font_color": bs_white,
    }
    h2 = {
        "font_size": 20,
        "center_across": True,
        "bg_color": bs_primary,
        "font_color": bs_white,
    }
    h3 = {
        "italic": True,
        "font_size": 15,
        "center_across": True,
        "bg_color": bs_primary,
        "font_color": bs_white,
    }
    summary_heading = {
        "bold": True,
        "font_size": 25,
        "center_across": True,
        "bg_color": bs_grey,
    }
    summary_row_title = {
        "bold": True,
        "font_size": 15,
        "align": "left",
        "valign": "top",
        "bg_color": bs_grey,
    }
    summary_row_data = {"font_size": 15, "align": "left", "bg_color": bs_grey}
    director_notes = {
        "font_size": 15,
        "align": "left",
        "valign": "top",
        "text_wrap": True,
        "bg_color": bs_warning,
    }
    detail_row_title = {
        "bold": True,
        "font_size": 20,
        "align": "left",
        "bg_color": bs_grey,
    }
    detail_row_title_number = {
        "bold": True,
        "font_size": 20,
        "align": "right",
        "bg_color": bs_grey,
    }
    detail_row_data = {"font_size": 15, "align": "left", "bg_color": bs_grey}
    detail_row_number = {"font_size": 15, "align": "right", "bg_color": bs_grey}
    detail_row_money = {
        "font_size": 15,
        "align": "right",
        "bg_color": bs_grey,
        "num_format": "$#,##0.00",
    }
    detail_row_free = {"font_size": 15, "align": "left", "bg_color": bs_dark_grey}
    info = {"italic": True, "font_size": 15, "align": "left"}
    section = {
        "bold": True,
        "font_size": 50,
        "center_across": True,
        "bg_color": bs_info,
        "font_color": bs_white,
    }
    link = {
        "bold": True,
        "font_size": 15,
        "center_across": True,
        "font_color": bs_danger,
    }
    attribution = {
        "italic": True,
        "font_size": 10,
        "center_across": True,
        "font_color": bs_danger,
    }


@login_required()
def xlsx_download(request, session_id):
    """Download XLS File of player details from a session"""

    # Get session and club data
    session = get_object_or_404(Session, pk=session_id)
    club = session.session_type.organisation

    # Check access
    club_role = f"club_sessions.sessions.{club.id}.edit"
    if not rbac_user_has_role(request.user, club_role):
        return rbac_forbidden(request, club_role)

    # Get the data
    session_entries, extras, mixed_dict, membership_type_dict = _xlsx_download_get_data(
        session, club
    )

    # Create HttpResponse to put the Excel file into
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response[
        "Content-Disposition"
    ] = f'attachment; filename="{session.description}.xlsx"'

    # Create an Excel file and add worksheets
    workbook = xlsxwriter.Workbook(response)
    summary_sheet = workbook.add_worksheet("Summary")
    details_sheet = workbook.add_worksheet("Table Fees")
    extras_sheet = workbook.add_worksheet("Extras") if extras else None

    # Do the headers and basic info
    details_row, extras_row, summary_row = _xlsx_download_basic_structure(
        workbook,
        summary_sheet,
        details_sheet,
        extras_sheet,
        session,
        club,
        request,
        extras,
    )

    # fill in the summary tab
    _xlsx_download_summary(session, summary_sheet, workbook, summary_row)

    # fill in the details tab
    _xlsx_download_details(
        mixed_dict,
        membership_type_dict,
        workbook,
        details_sheet,
        session_entries,
        extras,
        details_row,
    )

    # fill in the extras tab if we have any
    if extras:
        _xlsx_download_details_extras(
            extras, workbook, extras_sheet, extras_row, mixed_dict
        )

    workbook.close()

    return response


def _xlsx_download_get_data(session, club):
    """sub of xlsx download. Loads and formats data"""

    # Get dictionaries
    (
        session_entries,
        mixed_dict,
        session_fees,
        membership_type_dict,
    ) = load_session_entry_static(session, club)

    # Manipulate the data for the report
    for session_entry in session_entries:
        # Payment method
        if session_entry.payment_method:
            session_entry.payment_method_display = (
                session_entry.payment_method.payment_method
            )
        else:
            session_entry.payment_method_display = ""

        # Fudge the session entries for non-players to show as free if no payment taken
        if (
            session_entry.system_number in [PLAYING_DIRECTOR, SITOUT]
            and session_entry.fee == 0
        ):
            session_entry.payment_method_display = "Free"

    # Get extras
    extras = SessionMiscPayment.objects.filter(
        session_entry__session=session
    ).select_related("session_entry")

    return session_entries, extras, mixed_dict, membership_type_dict


def _xlsx_download_basic_structure(
    workbook, summary_sheet, details_sheet, extras_sheet, session, club, request, extras
):
    """add basic structure to tabs

    This puts in the headers etc on the tabs. It doesn't do any of the data.

    Extras and extras_sheet may be None in which case we don't process them

    """

    h1 = workbook.add_format(XLSXFormat.h1)
    h2 = workbook.add_format(XLSXFormat.h2)
    h3 = workbook.add_format(XLSXFormat.h3)
    summary_heading = workbook.add_format(XLSXFormat.summary_heading)
    summary_row_title = workbook.add_format(XLSXFormat.summary_row_title)
    detail_row_title = workbook.add_format(XLSXFormat.detail_row_title)
    detail_row_title_number = workbook.add_format(XLSXFormat.detail_row_title_number)
    summary_row_data = workbook.add_format(XLSXFormat.summary_row_data)
    info = workbook.add_format(XLSXFormat.info)
    link = workbook.add_format(XLSXFormat.link)
    section = workbook.add_format(XLSXFormat.section)
    director_notes = workbook.add_format(XLSXFormat.director_notes)

    # same headers on both/all tabs
    sheet_list = [summary_sheet, details_sheet]
    if extras:
        sheet_list.append(extras_sheet)

    # How wide for the title
    title_width = {summary_sheet: 4, details_sheet: 7, extras_sheet: 5}

    for sheet in sheet_list:
        # Put cursor away from title
        sheet.set_selection(6, 0, 6, 0)

        # Title
        sheet.merge_range(0, 0, 3, title_width[sheet], club.name, h1)
        sheet.merge_range(
            4,
            0,
            4,
            title_width[sheet],
            f"{session.description} on {session.session_date:%A %d %B %Y}",
            h2,
        )
        sheet.merge_range(
            5, 0, 5, title_width[sheet], f"Downloaded by {request.user.full_name}", h3
        )

        # Buffer
        sheet.merge_range(6, 0, 6, title_width[sheet], "")

    # Tell them about the other tab
    summary_sheet.write(
        7,
        3,
        "You can change to the Table Fees tab below to see a list of the transactions",
        info,
    )

    # Buttons
    #    summary_sheet.insert_button(8,3,{'macro':   'say_hello', 'caption': 'Press Me'})
    url = reverse("club_sessions:manage_session", kwargs={"session_id": session.id})
    summary_sheet.write_url(
        9, 3, f"https://{COBALT_HOSTNAME}{url}", link, string="Click to Open Session"
    )

    # Session details
    summary_sheet.merge_range(7, 0, 8, 1, "Session Details", summary_heading)
    summary_sheet.set_column("A:B", 30)

    # Status
    summary_sheet.write(9, 0, "Status", summary_row_title)
    if session.status == Session.SessionStatus.COMPLETE:
        summary_sheet.write(9, 1, "Complete", summary_row_data)
    else:
        summary_sheet.write(9, 1, "Incomplete", summary_row_data)

    # Director
    summary_sheet.write(10, 0, "Director", summary_row_title)
    summary_sheet.write(10, 1, f"{session.director}", summary_row_data)

    # Description
    summary_sheet.write(11, 0, "Description", summary_row_title)
    summary_sheet.write(11, 1, f"{session.description}", summary_row_data)

    # Date
    summary_sheet.write(12, 0, "Session Date", summary_row_title)
    summary_sheet.write(12, 1, f"{session.session_date:%A %d %B %Y}", summary_row_data)

    # Session Type
    summary_sheet.write(13, 0, "Session Type", summary_row_title)
    summary_sheet.write(13, 1, f"{session.session_type.name}", summary_row_data)

    # Time of Day
    summary_sheet.write(14, 0, "Time of Day", summary_row_title)
    summary_sheet.write(14, 1, f"{session.time_of_day}", summary_row_data)

    # Now we need to use row numbers
    summary_row_no = 15

    # Venue
    if session.venue:
        summary_sheet.write(summary_row_no, 0, "Venue", summary_row_title)
        summary_sheet.write(summary_row_no, 1, f"{session.venue}", summary_row_data)
        summary_row_no += 1

    # Buffer
    summary_sheet.merge_range(summary_row_no, 0, summary_row_no, 4, "")
    summary_row_no += 1

    # Notes
    if session.director_notes:
        summary_sheet.write(summary_row_no, 0, "Director Notes", summary_row_title)
        notes = strip_tags(session.director_notes)
        summary_sheet.merge_range(
            summary_row_no, 1, summary_row_no, 2, notes, director_notes
        )
        # Set height - we get about 70 characters per row and 25 whatevers per row height
        rows = math.ceil(len(notes) / 70)
        summary_sheet.set_row(summary_row_no, rows * 25)
        summary_row_no += 1

    # Now do headings on detail sheet
    details_sheet.merge_range(7, 0, 7, 7, "Table Fees", section)

    details_sheet.write(8, 0, "Table Number", detail_row_title)
    details_sheet.set_column("A:A", 35)
    details_sheet.write(8, 1, "Seat", detail_row_title)
    details_sheet.set_column("B:B", 15)
    details_sheet.write(8, 2, "Player Name", detail_row_title)
    details_sheet.set_column("C:C", 30)
    details_sheet.write(8, 3, f"{GLOBAL_ORG} Number", detail_row_title)
    details_sheet.set_column("D:D", 25)
    details_sheet.write(8, 4, "Membership", detail_row_title)
    details_sheet.set_column("E:E", 25)
    details_sheet.write(8, 5, "Payment Method", detail_row_title)
    details_sheet.set_column("F:F", 30)
    details_sheet.write(8, 6, "Fee", detail_row_title_number)
    details_sheet.set_column("G:G", 15)
    details_sheet.write(8, 7, "Processed", detail_row_title_number)
    details_sheet.set_column("H:H", 15)

    # now do headings on extras sheet if we have one
    if extras:
        extras_sheet.merge_range(7, 0, 7, 5, "Extras", section)

        extras_sheet.write(8, 0, "Player Name", detail_row_title)
        extras_sheet.set_column("A:A", 30)
        extras_sheet.write(8, 1, f"{GLOBAL_ORG} Number", detail_row_title)
        extras_sheet.set_column("B:B", 25)
        extras_sheet.write(8, 2, "Description", detail_row_title)
        extras_sheet.set_column("C:C", 50)
        extras_sheet.write(8, 3, "Payment Method", detail_row_title)
        extras_sheet.set_column("D:D", 30)
        extras_sheet.write(8, 4, "Fee", detail_row_title_number)
        extras_sheet.set_column("E:E", 15)
        extras_sheet.write(8, 5, "Processed", detail_row_title_number)
        extras_sheet.set_column("F:F", 15)

    # Return current row
    return 9, 9, summary_row_no


def _xlsx_download_summary(session, summary_sheet, workbook, summary_row_no):
    """fill in the summary data for the summary tab"""

    # formats
    attribution = workbook.add_format(XLSXFormat.attribution)

    # Get summary info
    payment_methods, extras = payment_method_summary(session)

    # Print payment_methods
    summary_row_no = _xlsx_download_summary_sub(
        "Payment Methods - Table Fees",
        payment_methods,
        summary_sheet,
        workbook,
        summary_row_no,
    )

    # Print extras if we have any
    if extras:
        # Buffer
        summary_sheet.merge_range(summary_row_no, 0, summary_row_no, 4, "")
        summary_row_no = _xlsx_download_summary_sub(
            "Payment Methods - Extras", extras, summary_sheet, workbook, summary_row_no
        )

    # Insert image and attribution
    summary_sheet.insert_image(
        summary_row_no + 2,
        0,
        "cobalt/static/assets/img/abftechlogo.png",
        {"x_scale": 0.17, "y_scale": 0.17},
    )
    summary_sheet.write(
        summary_row_no + 8, 0, f"{GLOBAL_TITLE} Version:{COBALT_VERSION}", attribution
    )


def _xlsx_download_summary_sub(
    heading, payment_types, summary_sheet, workbook, summary_row_no
):
    """fill in the summary data for the summary tab - subroutine

    Called with either payment_methods or extras as payment_types - both the same format of data

    """

    # formatting
    detail_row_title = workbook.add_format(XLSXFormat.detail_row_title)
    detail_row_title_number = workbook.add_format(XLSXFormat.detail_row_title_number)
    detail_row_data = workbook.add_format(XLSXFormat.detail_row_data)
    detail_row_money = workbook.add_format(XLSXFormat.detail_row_money)
    detail_row_number = workbook.add_format(XLSXFormat.detail_row_number)
    section = workbook.add_format(XLSXFormat.section)

    # Write headers
    summary_row_no += 1
    summary_sheet.merge_range(summary_row_no, 0, summary_row_no, 4, heading, section)
    summary_row_no += 1

    summary_sheet.write(summary_row_no, 0, "Payment Method", detail_row_title)
    summary_sheet.set_column("A:A", 30)
    summary_sheet.write(summary_row_no, 1, "Players Paid", detail_row_title_number)
    summary_sheet.set_column("B:B", 40)
    summary_sheet.write(summary_row_no, 2, "Players Unpaid", detail_row_title_number)
    summary_sheet.set_column("C:C", 40)
    summary_sheet.write(summary_row_no, 3, "Amount Paid", detail_row_title_number)
    summary_sheet.set_column("D:D", 40)
    summary_sheet.write(summary_row_no, 4, "Amount Unpaid", detail_row_title_number)
    summary_sheet.set_column("E:E", 40)
    summary_row_no += 1

    for payment_type in payment_types:
        payment_method_display = payment_type or "Free"
        summary_sheet.write(summary_row_no, 0, payment_method_display, detail_row_data)
        summary_sheet.write(
            summary_row_no,
            1,
            payment_types[payment_type]["paid"]["count"],
            detail_row_number,
        )
        summary_sheet.write(
            summary_row_no,
            2,
            payment_types[payment_type]["unpaid"]["count"],
            detail_row_number,
        )
        summary_sheet.write(
            summary_row_no,
            3,
            payment_types[payment_type]["paid"]["total"],
            detail_row_money,
        )
        summary_sheet.write(
            summary_row_no,
            4,
            payment_types[payment_type]["unpaid"]["total"],
            detail_row_money,
        )

        summary_row_no += 1

    return summary_row_no


def _xlsx_download_details(
    mixed_dict,
    membership_type_dict,
    workbook,
    details_sheet,
    session_entries,
    extras,
    details_row,
):
    """produce the session_entry and extras details for the detail tab"""

    # formatting
    detail_row_data = workbook.add_format(XLSXFormat.detail_row_data)
    detail_row_money = workbook.add_format(XLSXFormat.detail_row_money)
    detail_row_free = workbook.add_format(XLSXFormat.detail_row_free)

    # Write data rows
    for session_entry in session_entries:

        # Payment status
        is_paid = "Yes" if session_entry.is_paid else "No"

        # Default format - override if free
        format_type = detail_row_data
        format_type_money = detail_row_money

        # Don't show values for free players
        if session_entry.payment_method_display == "Free":
            is_paid = ""
            session_entry.fee = ""
            format_type = detail_row_free
            format_type_money = detail_row_free

        details_sheet.write(details_row, 0, session_entry.pair_team_number, format_type)
        details_sheet.write(details_row, 1, session_entry.seat, format_type)
        details_sheet.write(
            details_row,
            2,
            _get_name_for_csv(session_entry, mixed_dict).__str__(),
            format_type,
        )
        details_sheet.write(details_row, 3, session_entry.system_number, format_type)

        # Get membership type for members
        membership_type = membership_type_dict.get(session_entry.system_number)

        # If we have no membership type, then it will be a Guest or director or phantom
        if not membership_type:
            if session_entry.system_number in [PLAYING_DIRECTOR, SITOUT]:
                membership_type = ""
            else:
                membership_type = "Guest"

        details_sheet.write(details_row, 4, membership_type, format_type)
        details_sheet.write(
            details_row, 5, session_entry.payment_method_display, format_type
        )
        details_sheet.write(details_row, 6, session_entry.fee, format_type_money)
        details_sheet.write(details_row, 7, is_paid, format_type_money)

        details_row += 1


def _xlsx_download_details_extras(
    extras, workbook, extras_sheet, extras_row, mixed_dict
):
    """show extras on the detail tab if we have any"""

    # formatting
    detail_row_data = workbook.add_format(XLSXFormat.detail_row_data)
    detail_row_money = workbook.add_format(XLSXFormat.detail_row_money)

    for extra in extras:
        payment_made = "Yes" if extra.payment_made else "No"
        extras_sheet.write(
            extras_row,
            0,
            _get_name_for_csv(extra.session_entry, mixed_dict).__str__(),
            detail_row_data,
        )
        extras_sheet.write(
            extras_row, 1, extra.session_entry.system_number, detail_row_data
        )
        extras_sheet.write(extras_row, 2, extra.description, detail_row_data)
        extras_sheet.write(
            extras_row, 3, extra.payment_method.payment_method, detail_row_data
        )
        extras_sheet.write(extras_row, 4, extra.amount, detail_row_money)
        extras_sheet.write(extras_row, 5, payment_made, detail_row_money)

        extras_row += 1


@user_is_club_director()
def import_messages_htmx(request, club, session):
    """Show the messages generated when we imported the file"""

    if session.import_messages:
        messages = json.loads(session.import_messages)
    else:
        messages = None

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


def payment_method_summary_sub(payment_methods, payment_status_field):
    """sub of payment_method_summary to format the data for sessions and extras with all values including zeros
    for unpaid or paid amounts.

    The only difference between SessionEntry and SessionMiscPayment is the field name used to check if payment
    has been made. We accept this as a parameter.

    """

    # Fill in missing bits
    payment_methods_display = {}

    # Set up structure
    for payment_method in payment_methods:
        item = payment_method["payment_method__payment_method"]
        if item not in payment_methods_display:
            payment_methods_display[item] = {
                "paid": {"total": Decimal(0), "count": 0},
                "unpaid": {"total": Decimal(0), "count": 0},
            }

    # Fill in data
    for payment_method in payment_methods:
        item = payment_method["payment_method__payment_method"]
        if payment_method[payment_status_field]:
            payment_methods_display[item]["paid"] = {
                "total": payment_method["total"],
                "count": payment_method["count"],
            }
        else:
            payment_methods_display[item]["unpaid"] = {
                "total": payment_method["total"],
                "count": payment_method["count"],
            }

    return payment_methods_display


def payment_method_summary(session):
    """Summarise the payment methods and extras - used for both online and CSV reporting

    We don't use a database query to summarise the sessions as we need to manipulate the non-players
    for the report.

    """

    # Load the data
    session_entries = SessionEntry.objects.filter(session=session)

    # Go through and summarise
    payment_methods_display = {}
    for session_entry in session_entries:
        # Mark as Free if no payment method
        if session_entry.payment_method:
            payment_method = session_entry.payment_method.payment_method
        else:
            payment_method = "Free"
        # Also mark as Free for non-player and no fee set
        if (
            session_entry.system_number
            in [
                PLAYING_DIRECTOR,
                SITOUT,
            ]
            and session_entry.fee in [0, -99]
        ):
            payment_method = "Free"
            # Force to paid if Free
            session_entry.is_paid = True

        # Add to dict if not present
        if payment_method not in payment_methods_display:
            payment_methods_display[payment_method] = {
                "paid": {"total": Decimal(0), "count": 0},
                "unpaid": {"total": Decimal(0), "count": 0},
            }

        # Increment dict
        if session_entry.is_paid:
            payment_methods_display[payment_method]["paid"][
                "total"
            ] += session_entry.fee
            payment_methods_display[payment_method]["paid"]["count"] += 1
        else:
            payment_methods_display[payment_method]["unpaid"][
                "total"
            ] += session_entry.fee
            payment_methods_display[payment_method]["unpaid"]["count"] += 1

    # Get extras - this can use a query
    extras = (
        SessionMiscPayment.objects.filter(session_entry__session=session)
        .values("payment_method__payment_method", "payment_made")
        .annotate(total=Sum("amount"), count=Count("pk"))
        .order_by("payment_method__payment_method")
    )

    # format
    extras_display = payment_method_summary_sub(extras, "payment_made")

    return payment_methods_display, extras_display


@user_is_club_director()
def payment_methods_htmx(request, club, session):
    """Show summary by payment methods"""

    payment_methods, extras = payment_method_summary(session)

    return render(
        request,
        "club_sessions/reports/payment_methods_htmx.html",
        {"payment_methods": payment_methods, "extras": extras},
    )
