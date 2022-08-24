import codecs
import csv
import re

from django.shortcuts import render

from accounts.accounts_views.core import add_un_registered_user_with_mpc_data
from club_sessions.club_sessions_views.decorators import user_is_club_director
from club_sessions.forms import FileImportForm
from club_sessions.models import SessionEntry
from organisations.models import ClubLog
from payments.models import OrgPaymentMethod


@user_is_club_director()
def tab_import_htmx(request, club, session, messages=None, reload=False):
    """file upload tab

    Can be called directly (by HTMX on tab load) or after file upload. If after file upload then
    messages will contain any messages for the user and reload will be True.

    """

    existing_data = SessionEntry.objects.filter(session=session)

    return render(
        request,
        "club_sessions/manage/import_htmx.html",
        {
            "session": session,
            "club": club,
            "existing_data": existing_data,
            "messages": messages,
            "reload": reload,
        },
    )


def _import_file_upload_htmx_simple_csv(request, club, session):
    """Sub to handle simple CSV file. This is a generic format, not from the real world"""

    messages = []
    csv_file = request.FILES["file"]

    # get CSV reader (convert bytes to strings)
    csv_data = csv.reader(codecs.iterdecode(csv_file, "utf-8"))

    # skip header
    next(csv_data, None)

    # process file
    for line_no, line in enumerate(csv_data, start=2):
        response = _import_file_upload_htmx_process_line(
            line, line_no, session, club, request
        )
        if response:
            messages.append(response)

    return messages


def _import_file_upload_htmx_compscore2(request, club, session):
    """Sub to handle simple Compscore2 text file format

    File is like:

    North Shore Bridge Club	Compscore2W7
    WS WED 12.45PM OPEN
    Pr No	Player Names
    NORTH-SOUTH
    1	ALAN ADMIN / BETTY BUNTING (100 / 101)
    2	ANOTHER NAME / ANOTHER PARTNER (9999 / 99999)


    EAST-WEST
    1	COLIN CORGY / DEBBIE DYSON (102 / 103)
    2	PHANTOM / PHANTOM ( / )

    There is a tab character after the table number
    """

    messages = []
    text_file = request.FILES["file"]

    # We get North-South first
    current_direction = ["N", "S"]
    line_no = 0

    # Go through the lines looking for a valid line, or the change of direction line
    for line in text_file.readlines():

        # change bytes to str
        line = line.decode("utf-8")
        line_no += 1

        # See if direction changed
        if line.find("EAST-WEST") >= 0:
            current_direction = ["E", "W"]
            continue

        # Look for a valid line
        try:
            parts = line.split("\t")
        except ValueError:
            continue

        # try to get player numbers
        try:
            table = int(parts[0])
            player1, player2 = re.findall(r"\d+", parts[1])
        except ValueError:
            continue

        # ugly way to loop through player and direction
        player = player1
        for direction in current_direction:

            response = _import_file_upload_htmx_process_line(
                [table, direction, player], line_no, session, club, request
            )
            if response:
                messages.append(response)
            player = player2

    return messages


@user_is_club_director()
def import_file_upload_htmx(request, club, session):
    """Upload player names for a session"""

    messages = []

    form = FileImportForm(request.POST, request.FILES)
    if form.is_valid():

        SessionEntry.objects.filter(session=session).delete()

        if "generic_csv" in request.POST:
            messages = _import_file_upload_htmx_simple_csv(request, club, session)
        elif "compscore2" in request.POST:
            messages = _import_file_upload_htmx_compscore2(request, club, session)

        _import_file_upload_htmx_fill_in_table_gaps(session)

    else:
        print(form.errors)

    # Tell the parent function that the button was pressed
    reload = True

    return tab_import_htmx(request, messages=messages, reload=reload)


def _import_file_upload_htmx_process_line(line, line_no, session, club, request):
    """Process a single line from the import file"""

    message = None

    # Extract data
    try:
        table = line[0]
        direction = line[1]
        system_number = int(line[2])
    except ValueError:
        return f"Invalid data found on line {line_no}. Ignored."

    # If this user isn't registered then add them from the MPC
    user_type, response = add_un_registered_user_with_mpc_data(
        system_number, club, request.user
    )
    if response:
        ClubLog(
            organisation=club,
            actor=request.user,
            action=f"Added un-registered user {response['GivenNames']} {response['Surname']} through session import",
        ).save()
        message = (
            f"Added new user to system - {response['GivenNames']} {response['Surname']}"
        )

    # set payment method based upon user type
    if user_type == "user":
        payment_method = OrgPaymentMethod.objects.filter(
            organisation=club, active=True, payment_method="Bridge Credits"
        ).first()
        if not payment_method:
            payment_method = session.default_secondary_payment_method
    else:
        payment_method = session.default_secondary_payment_method

    # create session entry
    SessionEntry(
        session=session,
        pair_team_number=table,
        seat=direction,
        system_number=system_number,
        amount_paid=0,
        payment_method=payment_method,
    ).save()

    return message


def _import_file_upload_htmx_fill_in_table_gaps(session):
    """if there were missing positions in the file upload we want to fill them in. e.g if 3E had an error we don't
    want to have a missing seat"""

    # Get all data
    session_entries = SessionEntry.objects.filter(session=session)
    tables = {}
    for session_entry in session_entries:
        if session_entry.pair_team_number not in tables:
            tables[session_entry.pair_team_number] = []
        tables[session_entry.pair_team_number].append(session_entry.seat)

    # look for errors
    for table, value in tables.items():
        for compass in "NSEW":
            if compass not in value:
                SessionEntry(
                    session=session,
                    pair_team_number=table,
                    seat=compass,
                    amount_paid=0,
                    system_number=-1,
                ).save()
