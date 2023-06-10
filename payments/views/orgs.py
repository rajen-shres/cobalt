import csv
import datetime

import pytz
import xlsxwriter
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Min
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils import timezone, dateformat

from club_sessions.models import Session
from cobalt.settings import GLOBAL_CURRENCY_SYMBOL, BRIDGE_CREDITS, TIME_ZONE
from events.models import Event
from notifications.views.core import contact_member

from organisations.models import Organisation
from organisations.views.general import org_balance
from payments.forms import MemberTransferOrg
from payments.models import OrganisationTransaction
from payments.views.core import update_organisation, update_account
from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden
from utils.utils import cobalt_paginator
from utils.views.xls import XLSXStyles

TZ = pytz.timezone(TIME_ZONE)


def _format_date_helper(input_date):
    """format a date"""

    local_dt = timezone.localtime(input_date, TZ)
    return dateformat.format(local_dt, "Y-m-d H:i:s")


def _start_end_date_to_datetime(start_date, end_date):
    """helper to convert start and end date to date times"""

    # Convert dates to date times
    start_datetime_raw = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    start_datetime = timezone.make_aware(start_datetime_raw, TZ)
    end_datetime_raw = datetime.datetime.strptime(end_date, "%Y-%m-%d")
    end_datetime = timezone.make_aware(end_datetime_raw, TZ)

    return start_datetime, end_datetime


@login_required()
def statement_org(request, org_id):
    """Organisation statement view.

    Basic view of statement showing transactions in a web page.

    Args:
        request: standard request object
        org_id: organisation to view

    Returns:
        HTTPResponse

    """

    organisation = get_object_or_404(Organisation, pk=org_id)

    admin_view = rbac_user_has_role(request.user, "payments.global.view")

    if (
        not rbac_user_has_role(request.user, "payments.manage.%s.view" % org_id)
        and not rbac_user_has_role(request.user, "payments.manage.%s.edit" % org_id)
        and not admin_view
    ):
        return rbac_forbidden(request, "payments.manage.%s.view" % org_id)

    # get balance
    balance = org_balance(organisation, True)

    # get summary
    today = timezone.now()
    ref_date = today - datetime.timedelta(days=30)
    summary = (
        OrganisationTransaction.objects.filter(
            organisation=organisation, created_date__gte=ref_date
        )
        .values("type")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )

    total = 0.0
    for item in summary:
        total += float(item["total"])

    # get details
    events_list = OrganisationTransaction.objects.filter(
        organisation=organisation
    ).order_by("-created_date")

    things = cobalt_paginator(request, events_list)

    page_balance = {}

    if things:
        page_balance["closing_balance"] = things[0].balance
        page_balance["closing_date"] = things[0].created_date
        earliest = things[len(things) - 1]
        page_balance["opening_balance"] = earliest.balance - earliest.amount
        page_balance["opening_date"] = earliest.created_date

    return render(
        request,
        "payments/orgs/statement_org.html",
        {
            "things": things,
            "balance": balance,
            "org": organisation,
            "summary": summary,
            "total": total,
            "page_balance": page_balance,
            "admin_view": admin_view,
        },
    )


@login_required()
def statement_csv_org(request, org_id):
    """Organisation statement CSV.

    Args:
        request: standard request object
        org_id: organisation to view

    Returns:
        HTTPResponse: CSV

    """

    # TODO: Retire this and replace with the club admin version

    organisation = get_object_or_404(Organisation, pk=org_id)

    if not rbac_user_has_role(request.user, "payments.manage.%s.view" % org_id):
        if not rbac_user_has_role(request.user, "payments.global.view"):
            return rbac_forbidden(request, "payments.manage.%s.view" % org_id)

    # get details
    events_list = OrganisationTransaction.objects.filter(
        organisation=organisation
    ).order_by("-created_date")

    local_dt = timezone.localtime(timezone.now(), TZ)
    today = dateformat.format(local_dt, "Y-m-d H:i:s")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="statement.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [organisation.name, "Downloaded by %s" % request.user.full_name, today]
    )
    writer.writerow(
        [
            "Date",
            "Counterparty",
            "Reference",
            "Type",
            "Description",
            "Amount",
            "Balance",
        ]
    )

    for row in events_list:
        counterparty = ""
        if row.member:
            counterparty = row.member
        if row.other_organisation:
            counterparty = row.other_organisation

        local_dt = timezone.localtime(row.created_date, TZ)
        writer.writerow(
            [
                dateformat.format(local_dt, "Y-m-d H:i:s"),
                counterparty,
                row.reference_no,
                row.type,
                row.description,
                row.amount,
                row.balance,
            ]
        )

    return response


def organisation_transactions_get_data(club, start_date, end_date):
    """get the data for both the CSV and Excel downloads"""

    # Convert dates to date times
    start_datetime, end_datetime = _start_end_date_to_datetime(start_date, end_date)

    # run query
    organisation_transactions = (
        OrganisationTransaction.objects.filter(
            organisation=club,
            created_date__gte=start_datetime,
            created_date__lte=end_datetime,
        )
        .order_by("-created_date")
        .select_related("member")
    )

    # Get session ids
    session_ids = (
        OrganisationTransaction.objects.filter(
            organisation=club,
            created_date__gte=start_datetime,
            created_date__lte=end_datetime,
        )
        .filter(club_session_id__isnull=False)
        .values_list("club_session_id", flat=True)
        .distinct("club_session_id")
    )

    # Get session names
    session_names = Session.objects.filter(pk__in=session_ids)
    session_names_dict = {}
    for session_name in session_names:
        session_names_dict[session_name.id] = session_name.description

    # Get event ids
    event_ids = (
        OrganisationTransaction.objects.filter(
            organisation=club,
            created_date__gte=start_datetime,
            created_date__lte=end_datetime,
        )
        .filter(event_id__isnull=False)
        .values_list("event_id", flat=True)
        .distinct("event_id")
    )

    # Get event names
    event_names = Event.objects.filter(pk__in=event_ids).select_related("congress")
    event_names_dict = {}
    for event_name in event_names:
        event_names_dict[
            event_name.id
        ] = f"{event_name.congress.name} - {event_name.event_name}"

    # Augment data
    for organisation_transaction in organisation_transactions:

        # Session name
        if organisation_transaction.club_session_id:
            try:
                organisation_transaction.club_session_name = session_names_dict[
                    organisation_transaction.club_session_id
                ]
            except KeyError:
                organisation_transaction.club_session_name = (
                    "Not found - session may be deleted"
                )
        else:
            organisation_transaction.club_session_name = ""

        # Event name
        if organisation_transaction.event_id:
            organisation_transaction.event_name = event_names_dict[
                organisation_transaction.event_id
            ]
        else:
            organisation_transaction.event_name = ""

        # counterparty
        if organisation_transaction.member:
            organisation_transaction.counterparty = (
                organisation_transaction.member.__str__()
            )
        elif organisation_transaction.other_organisation:
            organisation_transaction.counterparty = (
                organisation_transaction.other_organisation.__str__()
            )
        else:
            organisation_transaction.counterparty = ""

        # Date
        organisation_transaction.formatted_date = _format_date_helper(
            organisation_transaction.created_date
        )

    return organisation_transactions


def organisation_transactions_csv_download(request, club, start_date, end_date):
    """Organisation CSV download. Internal function, security is handled by the calling function.

    Returns a CSV.

    """

    # get details
    organisation_transactions = organisation_transactions_get_data(
        club, start_date, end_date
    )

    # Download datetime
    local_dt = timezone.localtime(timezone.now(), TZ)
    today = dateformat.format(local_dt, "Y-m-d H:i:s")

    # Create return object
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="statement.csv"'

    # build CSV header
    writer = csv.writer(response)
    writer.writerow([club.name, f"Downloaded by {request.user.full_name}", today])
    writer.writerow(
        [
            "Date",
            "Counterparty",
            "Reference",
            "id",
            "Type",
            "Description",
            "Session ID",
            "Session Name",
            "Event ID",
            "Event Name",
            "Amount",
            "Balance",
        ]
    )

    # Add data rows
    for row in organisation_transactions:

        writer.writerow(
            [
                row.formatted_date,
                row.counterparty,
                row.reference_no,
                row.id,
                row.type,
                row.description,
                row.club_session_id,
                row.club_session_name,
                row.event_id,
                row.event_name,
                row.amount,
                row.balance,
            ]
        )

    return response


def _organisation_transactions_xls_header(
    request, club, sheet, formats, title, subtitle, width
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
    sheet.merge_range(6, 0, 9, width, subtitle, formats.h1_success)

    # Buffer
    sheet.merge_range(10, 0, 10, width, "")


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
        width=11,
    )

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
    details_sheet.write(11, 11, "Balance", formats.detail_row_title_number)
    details_sheet.set_column("L:L", 15)

    # Add data
    organisation_transactions = organisation_transactions_get_data(
        club, start_date, end_date
    )

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


def _organisation_transactions_xls_download_sessions(
    formats, sessions_sheet, request, club, start_date, end_date
):
    """sub of organisation_transactions_xls_download to handle the sessions tab"""

    _organisation_transactions_xls_header(
        request,
        club,
        sessions_sheet,
        formats,
        f"Download for {start_date} to {end_date}",
        "Sessions",
        11,
    )

    # Now do data headings
    sessions_sheet.write(11, 0, "First Payment Date/Time", formats.detail_row_title)
    sessions_sheet.set_column("A:A", 35)
    sessions_sheet.write(11, 1, "Session ID", formats.detail_row_title_number)
    sessions_sheet.set_column("B:B", 20)
    sessions_sheet.write(11, 2, "Session Name", formats.detail_row_title)
    sessions_sheet.set_column("C:C", 60)
    sessions_sheet.write(11, 3, "Amount", formats.detail_row_title_number)
    sessions_sheet.set_column("D:D", 15)

    # Convert dates to date times
    start_datetime, end_datetime = _start_end_date_to_datetime(start_date, end_date)

    # run query
    session_summaries = (
        OrganisationTransaction.objects.filter(organisation=club)
        .filter(created_date__gte=start_datetime, created_date__lte=end_datetime)
        .exclude(club_session_id=None)
        .order_by("-club_session_id")
        .values("description", "club_session_id")
        .annotate(amount=Sum("amount"))
        .annotate(created_date=Min("created_date"))
    )

    sessions_sheet.write(
        10,
        0,
        "This has data for session within the date range. Payments may have occurred outside the date range.",
        formats.h3_success,
    )

    print(session_summaries)

    for row_no, session_summary in enumerate(session_summaries, start=12):
        sessions_sheet.write(
            row_no,
            0,
            _format_date_helper(session_summary["created_date"]),
            formats.detail_row_data,
        )
        sessions_sheet.write(
            row_no, 1, session_summary["club_session_id"], formats.detail_row_number
        )
        sessions_sheet.write(
            row_no, 2, session_summary["amount"], formats.detail_row_data
        )
        sessions_sheet.write(
            row_no, 3, session_summary["amount"], formats.detail_row_money
        )


def organisation_transactions_xls_download(request, club, start_date, end_date):
    """Download XLS File of org transactions"""

    # Create HttpResponse to put the Excel file into
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="statement.xlsx"'

    # Create an Excel file and add worksheets
    workbook = xlsxwriter.Workbook(response)
    details_sheet = workbook.add_worksheet("Transactions")
    sessions_sheet = workbook.add_worksheet("Sessions")
    # events_sheet = workbook.add_worksheet("Events")

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

    workbook.close()

    return response


def statement_org_summary_ajax(request, org_id, range):
    """Called by the org statement when the summary date range changes

    Args:
        request (HTTPRequest): standard request object
        org_id(int): pk of the org to query
        range(str): range to include in summary

    Returns:
        HTTPResponse: data for table

    """
    if request.method == "GET":

        organisation = get_object_or_404(Organisation, pk=org_id)

        if (
            not rbac_user_has_role(request.user, "payments.manage.%s.view" % org_id)
            and not rbac_user_has_role(request.user, "payments.manage.%s.edit" % org_id)
            and not rbac_user_has_role(request.user, "payments.global.view")
        ):
            return rbac_forbidden(request, "payments.manage.%s.view" % org_id)

        if range == "All":
            summary = (
                OrganisationTransaction.objects.filter(organisation=organisation)
                .values("type")
                .annotate(total=Sum("amount"))
                .order_by("-total")
            )
        else:
            days = int(range)
            today = timezone.now()
            ref_date = today - datetime.timedelta(days=days)
            summary = (
                OrganisationTransaction.objects.filter(
                    organisation=organisation, created_date__gte=ref_date
                )
                .values("type")
                .annotate(total=Sum("amount"))
                .order_by("-total")
            )

    total = 0.0
    for item in summary:
        total += float(item["total"])

    return render(
        request,
        "payments/orgs/statement_org_summary_ajax.html",
        {"summary": summary, "total": total},
    )


@login_required()
def member_transfer_org(request, org_id):
    """Allows an organisation to transfer money to a member

    Args:
        request (HTTPRequest): standard request object
        org_id (int): organisation doing the transfer

    Returns:
        HTTPResponse
    """

    organisation = get_object_or_404(Organisation, pk=org_id)

    if not rbac_user_has_role(
        request.user, "payments.manage.%s.edit" % org_id
    ) and not rbac_user_has_role(request.user, "payments.global.edit"):
        return rbac_forbidden(request, "payments.manage.%s.edit" % org_id)

    balance = org_balance(organisation)

    if request.method == "POST":
        form = MemberTransferOrg(request.POST, balance=balance)
        if form.is_valid():
            member = form.cleaned_data["transfer_to"]
            amount = form.cleaned_data["amount"]
            description = form.cleaned_data["description"]

            # Org transaction
            update_organisation(
                organisation=organisation,
                description=description,
                amount=-amount,
                payment_type="Member Transfer",
                member=member,
            )

            update_account(
                member=member,
                amount=amount,
                description=description,
                payment_type="Org Transfer",
                organisation=organisation,
            )

            # Notify member
            email_body = f"""<b>{organisation}</b> has transferred {GLOBAL_CURRENCY_SYMBOL}{amount:.2f}
                            into your {BRIDGE_CREDITS} account.
                            <br><br>
                            The description was: {description}.
                            <br><br>
                            Please contact {organisation} directly if you have any queries.
                            This transfer was made by {request.user}.
                            <br><br>"""

            # send
            contact_member(
                member=member,
                msg="Transfer from %s - %s%s"
                % (organisation, GLOBAL_CURRENCY_SYMBOL, amount),
                contact_type="Email",
                html_msg=email_body,
                link="/payments",
                subject="Transfer from %s" % organisation,
            )

            msg = "Transferred %s%s to %s" % (
                GLOBAL_CURRENCY_SYMBOL,
                amount,
                member,
            )
            messages.success(request, msg, extra_tags="cobalt-message-success")
            return redirect("payments:statement_org", org_id=organisation.id)
        else:
            print(form.errors)
    else:
        form = MemberTransferOrg(balance=balance)

    return render(
        request,
        "payments/orgs/member_transfer_org.html",
        {"form": form, "balance": balance, "org": organisation},
    )


@login_required()
def get_org_fees(request, org_id):
    """Get the ABF fees associated with this organisation"""

    org = get_object_or_404(Organisation, pk=org_id)
    return HttpResponse(org.settlement_fee_percent)
