import xlsxwriter
from django.db.models import Sum
from django.http import HttpResponse

from club_sessions.models import Session
from cobalt.settings import GLOBAL_CURRENCY_SYMBOL
from payments.models import OrganisationTransaction
from payments.views.org_report.data import (
    organisation_transactions_by_date_range,
    event_payments_summary_by_date_range,
    sessions_and_payments_by_date_range,
    combined_view_events_sessions_other,
)
from utils.views.xls import XLSXStyles


def _organisation_transactions_xls_header(
    request, club, sheet, formats, title, subtitle, subtitle_style, width
):
    """Add a title to a sheet"""

    # Put cursor away from title
    sheet.set_selection(10, 0, 10, 0)

    # Title
    sheet.merge_range(0, 0, 3, width, club.name, formats.h1_info)
    sheet.merge_range(4, 0, 4, width, title, formats.h2_info)
    sheet.merge_range(
        5, 0, 5, width, f"Downloaded by {request.user.full_name}", formats.h3_info
    )
    sheet.merge_range(6, 0, 9, width, subtitle, subtitle_style)

    # Buffer
    sheet.merge_range(10, 0, 10, width, "")


def _details_headings(details_sheet, formats, show_balance=True):
    """common headings for details and combined view"""

    # Now do data headings
    details_sheet.write(11, 0, "Date/Time", formats.detail_row_title)
    details_sheet.set_column("A:A", 25)
    details_sheet.write(11, 1, "Counterparty", formats.detail_row_title)
    details_sheet.set_column("B:B", 35)
    details_sheet.write(11, 2, "Reference", formats.detail_row_title)
    details_sheet.set_column("C:C", 25)
    details_sheet.write(11, 3, "Id", formats.detail_row_title_number)
    details_sheet.set_column("D:D", 10)
    details_sheet.write(11, 4, "Transaction Type", formats.detail_row_title)
    details_sheet.set_column("E:E", 25)
    details_sheet.write(11, 5, "Description", formats.detail_row_title)
    details_sheet.set_column("F:F", 60)
    details_sheet.write(11, 6, "Session ID", formats.detail_row_title_number)
    details_sheet.set_column("G:G", 20)
    details_sheet.write(11, 7, "Session Name", formats.detail_row_title)
    details_sheet.set_column("H:H", 60)
    details_sheet.write(11, 8, "Event ID", formats.detail_row_title_number)
    details_sheet.set_column("I:I", 15)
    details_sheet.write(11, 9, "Event Name", formats.detail_row_title)
    details_sheet.set_column("J:J", 60)
    details_sheet.write(11, 10, "Amount", formats.detail_row_title_number)
    details_sheet.set_column("K:K", 15)
    if show_balance:
        details_sheet.write(11, 11, "Balance", formats.detail_row_title_number)
        details_sheet.set_column("L:L", 15)


def _organisation_transactions_xls_download_details(
    formats, details_sheet, request, club, start_date, end_date
):
    """sub of organisation_transactions_xls_download to handle the details tab"""

    _organisation_transactions_xls_header(
        request,
        club,
        details_sheet,
        formats,
        title=f"Download for {start_date} to {end_date}",
        subtitle="Transactions",
        subtitle_style=formats.h1_success,
        width=11,
    )

    # Now do data headings
    _details_headings(details_sheet, formats)

    # Get data
    organisation_transactions = organisation_transactions_by_date_range(
        club, start_date, end_date
    )

    # Data rows
    for row_no, org_tran in enumerate(organisation_transactions, start=12):
        details_sheet.write(row_no, 0, org_tran.formatted_date, formats.detail_row_data)
        details_sheet.write(row_no, 1, org_tran.counterparty, formats.detail_row_data)
        details_sheet.write(row_no, 2, org_tran.reference_no, formats.detail_row_data)
        details_sheet.write(row_no, 3, org_tran.id, formats.detail_row_number)
        details_sheet.write(row_no, 4, org_tran.type, formats.detail_row_data)
        details_sheet.write(row_no, 5, org_tran.description, formats.detail_row_data)
        details_sheet.write(
            row_no, 6, org_tran.club_session_id, formats.detail_row_number
        )
        details_sheet.write(
            row_no, 7, org_tran.club_session_name, formats.detail_row_data
        )
        details_sheet.write(row_no, 8, org_tran.event_id, formats.detail_row_number)
        details_sheet.write(row_no, 9, org_tran.event_name, formats.detail_row_data)
        details_sheet.write(row_no, 10, org_tran.amount, formats.detail_row_money)
        details_sheet.write(row_no, 11, org_tran.balance, formats.detail_row_money)


def _organisation_transactions_xls_download_combined(
    formats, details_sheet, request, club, start_date, end_date
):
    """sub of organisation_transactions_xls_download to handle the combined tab"""

    _organisation_transactions_xls_header(
        request,
        club,
        details_sheet,
        formats,
        title=f"Download for {start_date} to {end_date}",
        subtitle="Combined",
        subtitle_style=formats.h1_success,
        width=10,
    )

    # Now do data headings
    _details_headings(details_sheet, formats, show_balance=False)

    # write warning
    details_sheet.write(
        10,
        0,
        "Events and Sessions use their start date, payments can occur on different dates.",
        formats.h3_primary,
    )

    # Get data
    organisation_transactions = combined_view_events_sessions_other(
        club, start_date, end_date
    )

    # Data rows
    for row_no, org_tran_tuple in enumerate(organisation_transactions, start=12):
        org_tran = org_tran_tuple[1]
        details_sheet.write(
            row_no, 0, org_tran.get("formatted_date", ""), formats.detail_row_data
        )
        details_sheet.write(
            row_no, 1, org_tran.get("counterparty", "Multiple"), formats.detail_row_data
        )
        details_sheet.write(
            row_no, 2, org_tran.get("reference_no", "-"), formats.detail_row_data
        )
        details_sheet.write(
            row_no, 3, org_tran.get("id", "-"), formats.detail_row_number
        )
        details_sheet.write(
            row_no, 4, org_tran.get("type", ""), formats.detail_row_data
        )
        details_sheet.write(
            row_no, 5, org_tran.get("description", ""), formats.detail_row_data
        )
        details_sheet.write(
            row_no, 6, org_tran.get("club_session_id", ""), formats.detail_row_number
        )
        details_sheet.write(
            row_no, 7, org_tran.get("club_session_name", ""), formats.detail_row_data
        )
        details_sheet.write(
            row_no, 8, org_tran.get("event_id", ""), formats.detail_row_number
        )
        details_sheet.write(
            row_no, 9, org_tran.get("event_name", ""), formats.detail_row_data
        )
        details_sheet.write(
            row_no, 10, org_tran.get("amount", ""), formats.detail_row_money
        )
        if "amount_outside_range" in org_tran:
            msg = f"Payments of {GLOBAL_CURRENCY_SYMBOL}{org_tran['amount_outside_range']} were made outside the date range"
            details_sheet.write(row_no, 11, msg, formats.warning_message)
            details_sheet.set_column("L:L", 100)


def _organisation_transactions_xls_download_sessions(
    formats, sessions_sheet, request, club, start_date, end_date
):
    """sub of organisation_transactions_xls_download to handle the sessions tab"""

    # Add main heading
    _organisation_transactions_xls_header(
        request,
        club,
        sessions_sheet,
        formats,
        title=f"Download for {start_date} to {end_date}",
        subtitle="Sessions",
        subtitle_style=formats.h1_primary,
        width=3,
    )

    # Now do data headings
    sessions_sheet.write(11, 0, "Session Date", formats.detail_row_title)
    sessions_sheet.set_column("A:A", 35)
    sessions_sheet.write(11, 1, "Session ID", formats.detail_row_title_number)
    sessions_sheet.set_column("B:B", 20)
    sessions_sheet.write(11, 2, "Session Name", formats.detail_row_title)
    sessions_sheet.set_column("C:C", 60)
    sessions_sheet.write(11, 3, "Amount", formats.detail_row_title_number)
    sessions_sheet.set_column("D:D", 15)

    # write warning
    sessions_sheet.write(
        10,
        0,
        "This has data for session within the date range. Payments may have occurred outside the date range.",
        formats.h3_primary,
    )

    # Get sessions in this date range and associated payments
    sessions_in_range, payments_dict = sessions_and_payments_by_date_range(
        club, start_date, end_date
    )

    # write data
    for row_no, session_in_range_id in enumerate(sessions_in_range, start=12):

        amount = payments_dict.get(session_in_range_id, "No Payments")

        sessions_sheet.write(
            row_no,
            0,
            f"{sessions_in_range[session_in_range_id].session_date}",
            formats.detail_row_data,
        )
        sessions_sheet.write(row_no, 1, session_in_range_id, formats.detail_row_number)
        sessions_sheet.write(
            row_no,
            2,
            sessions_in_range[session_in_range_id].description,
            formats.detail_row_data,
        )
        sessions_sheet.write(row_no, 3, amount, formats.detail_row_money)


def _organisation_transactions_xls_download_events(
    formats, sessions_sheet, request, club, start_date, end_date
):
    """sub of organisation_transactions_xls_download to handle the events tab"""

    # Add main heading
    _organisation_transactions_xls_header(
        request,
        club,
        sessions_sheet,
        formats,
        title=f"Download for {start_date} to {end_date}",
        subtitle="Events",
        subtitle_style=formats.h1_warning,
        width=4,
    )

    # Now do data headings
    sessions_sheet.write(11, 0, "Event Start Date", formats.detail_row_title)
    sessions_sheet.set_column("A:A", 35)
    sessions_sheet.write(11, 1, "Event ID", formats.detail_row_title_number)
    sessions_sheet.set_column("B:B", 20)
    sessions_sheet.write(11, 2, "Congress", formats.detail_row_title)
    sessions_sheet.set_column("C:C", 60)
    sessions_sheet.write(11, 3, "Event Name", formats.detail_row_title)
    sessions_sheet.set_column("D:D", 60)
    sessions_sheet.write(11, 4, "Amount", formats.detail_row_title_number)
    sessions_sheet.set_column("E:E", 15)

    # Get sessions in this date range and associated payments
    event_data = event_payments_summary_by_date_range(club, start_date, end_date)

    # write data
    for row_no, event_id in enumerate(event_data, start=12):

        print(event_data[event_id]["start_date"])

        sessions_sheet.write(
            row_no, 0, f"{event_data[event_id]['start_date']}", formats.detail_row_data
        )
        sessions_sheet.write(row_no, 1, event_id, formats.detail_row_number)
        sessions_sheet.write(
            row_no, 2, event_data[event_id]["congress_name"], formats.detail_row_data
        )
        sessions_sheet.write(
            row_no, 3, event_data[event_id]["event_name"], formats.detail_row_data
        )
        sessions_sheet.write(
            row_no, 4, event_data[event_id]["amount"], formats.detail_row_money
        )

        if event_data[event_id]["amount_outside_range"] != 0:
            msg = f"Payments of {GLOBAL_CURRENCY_SYMBOL}{event_data[event_id]['amount_outside_range']} were made outside the date range"
            sessions_sheet.write(row_no, 5, msg, formats.warning_message)
            sessions_sheet.set_column("F:F", 100)


def organisation_transactions_xls_download(request, club, start_date, end_date):
    """Download XLS File of org transactions"""

    combined_view_events_sessions_other(club, start_date, end_date)

    # Create HttpResponse to put the Excel file into
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="statement.xlsx"'

    # Create an Excel file and add worksheets
    workbook = xlsxwriter.Workbook(response)
    details_sheet = workbook.add_worksheet("Transactions")
    sessions_sheet = workbook.add_worksheet("Sessions")
    events_sheet = workbook.add_worksheet("Events")
    combined_sheet = workbook.add_worksheet("Combined")

    # Create styles
    formats = XLSXStyles(workbook)

    # Details tab
    _organisation_transactions_xls_download_details(
        formats, details_sheet, request, club, start_date, end_date
    )

    # Sessions tab
    _organisation_transactions_xls_download_sessions(
        formats, sessions_sheet, request, club, start_date, end_date
    )

    # Events tab
    _organisation_transactions_xls_download_events(
        formats, events_sheet, request, club, start_date, end_date
    )

    # Combination tab
    _organisation_transactions_xls_download_combined(
        formats, combined_sheet, request, club, start_date, end_date
    )

    workbook.close()

    return response
