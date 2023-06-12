import csv

import pytz
from django.http import HttpResponse
from django.utils import timezone, dateformat

from cobalt.settings import TIME_ZONE
from payments.views.org_report.data import organisation_transactions_by_date_range

TZ = pytz.timezone(TIME_ZONE)


def organisation_transactions_csv_download(request, club, start_date, end_date):
    """Organisation CSV download. Internal function, security is handled by the calling function.

    Returns a CSV.

    """

    # get details
    organisation_transactions = organisation_transactions_by_date_range(
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
