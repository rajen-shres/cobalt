import codecs
import csv
import io
import json
import re

from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required

from accounts.views.core import add_un_registered_user_with_mpc_data
from club_sessions.views.core import PLAYING_DIRECTOR, VISITOR, SITOUT
from club_sessions.forms import FileImportForm
from club_sessions.models import SessionEntry, SessionMiscPayment, Session, SessionType
from organisations.models import ClubLog, Organisation
from organisations.views.club_menu import tab_sessions_htmx
from payments.models import OrgPaymentMethod
from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden


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
        # Add dummy name to file import
        line.append("Unknown")
        response = _import_file_upload_htmx_process_line(
            line, line_no, session, club, request
        )
        if response:
            messages.append(response)

    session.import_messages = json.dumps(messages)
    session.save()


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

    lines = text_file.readlines()

    # Go through the lines looking for a valid line, or the change of direction line
    for line in lines:

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

        # try to get player numbers and names
        # line is (e.g.):
        # 1(tab char)PLAYING DIRECTOR / SIMON SEZ (1 / 118)
        try:
            table = int(parts[0])
            # Any digits are the player numbers
            player1, player2 = re.findall(r"\d+", parts[1])

            # For player names, look for anything before "/" and anything after upto "("
            player_1_file_name, player2_file_name = re.findall(
                r"(.+)\s\/\s(.+)\(", parts[1]
            )[0]
            player2_file_name = player2_file_name.strip()

        except ValueError:
            continue

        # ugly way to loop through player and direction
        player = player1
        player_file_name = player_1_file_name
        for direction in current_direction:

            response = _import_file_upload_htmx_process_line(
                [table, direction, player, player_file_name],
                line_no,
                session,
                club,
                request,
            )
            if response:
                messages.append(response)
            player = player2
            player_file_name = player2_file_name

    # The session title is the second line - strip anything dodgy
    session.description = lines[1].decode("utf-8")[:50]

    # strip anything dodgy
    session.description = re.sub(r"[^0-9a-zA-Z\w]+", " ", session.description)

    session.import_messages = json.dumps(messages)
    session.save()


def _import_file_upload_htmx_compscore3(request, club, session):
    """Sub to handle simple Compscore3 CSV file format

        File is like:

    PairNumber,	Name,	ABF No,	Initial Seating,	Phone
    1,	SHIRLEY RUTTER,	936235,	1-NS,
    1,	YEUNG CHEUNG,	936510,	1-NS,
    2,	CHRISTINE GRECH,	447633,	2-NS,
    2,	LEO VILENSKY,	1049471,	2-NS,

    For a visitor, sit out or playing director we get no system_number. For a sit out the name is PHANTOM

    """

    messages = []

    # Muck about with file format
    text_file = request.FILES["file"]
    file = text_file.read().decode("utf-8")
    reader = csv.reader(io.StringIO(file))

    # Skip header
    next(reader)

    # count the rows, odds are N or E, evens are S or W
    for row_no, row in enumerate(reader, start=1):
        player_file_name = row[1]
        system_number = row[2]
        initial_seating = row[3]
        table, both_direction = initial_seating.split("-")
        direction = both_direction[1] if row_no % 2 == 0 else both_direction[0]

        # Handle sit out and playing director
        if not system_number:
            if player_file_name.strip() == "PHANTOM":
                system_number = SITOUT
            elif player_file_name.find("DIRECTOR") >= 0:
                system_number = PLAYING_DIRECTOR
            else:
                system_number = VISITOR

        response = _import_file_upload_htmx_process_line(
            [table, direction, system_number, player_file_name],
            row_no,
            session,
            club,
            request,
        )
        if response:
            messages.append(response)

    # The session title is part of the file name
    session.description = text_file.name

    # Reformat
    session.description = session.description.replace(".csv", "")
    session.description = session.description.replace("Names - ", "")

    # strip anything dodgy
    session.description = re.sub(r"[^0-9a-zA-Z\w]+", " ", session.description)[:50]

    session.import_messages = json.dumps(messages)
    session.save()


@login_required()
def import_file_upload_htmx(request):
    """

    Upload player names for a session

    Called from club admin to create a new session and fill it with players from the uploaded file

    """

    # Get club
    club = get_object_or_404(Organisation, pk=request.POST.get("club_id"))

    # Check access - we don't use the decorator as we don't have a session yet
    club_role = f"club_sessions.sessions.{club.id}.edit"
    if not rbac_user_has_role(request.user, club_role):
        return rbac_forbidden(request, club_role)

    form = FileImportForm(request.POST, request.FILES)
    if form.is_valid():

        # If we got a session type then use that, otherwise use first (only) one
        if "session_type" in request.POST:
            session_type = get_object_or_404(
                SessionType, pk=request.POST.get("session_type")
            )
        else:
            session_type = SessionType.objects.filter(organisation=club).first()

        session = Session(
            director=request.user,
            session_type=session_type,
            description="Added session",
            default_secondary_payment_method=club.default_secondary_payment_method,
        )
        session.save()

        try:

            if "generic_csv" in request.POST:
                _import_file_upload_htmx_simple_csv(request, club, session)
            elif "compscore2" in request.POST:
                _import_file_upload_htmx_compscore2(request, club, session)
            elif "compscore3" in request.POST:
                _import_file_upload_htmx_compscore3(request, club, session)

        except (IndexError, ValueError):
            SessionEntry.objects.filter(session=session).delete()
            session.delete()
            return tab_sessions_htmx(request, message="Invalid file format")

        _import_file_upload_htmx_fill_in_table_gaps(session)

    else:
        print(form.errors)
        session = None

    response = tab_sessions_htmx(request)
    if session:
        response[
            "HX-Trigger"
        ] = f"""{{"file_upload_finished":{{"id": "{session.id}" }}}}"""
    return response


def _import_file_upload_htmx_process_line(line, line_no, session, club, request):
    """Process a single line from the import file"""

    message = None

    # Extract data
    try:
        table = line[0]
        direction = line[1]
        system_number = int(line[2])
        player_file_name = line[3]
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
    if user_type == "user" and system_number not in [VISITOR, PLAYING_DIRECTOR, SITOUT]:
        payment_method = OrgPaymentMethod.objects.filter(
            organisation=club, active=True, payment_method="Bridge Credits"
        ).first()
        if not payment_method:
            payment_method = session.default_secondary_payment_method
    else:
        payment_method = session.default_secondary_payment_method

    # See if this club is using the last payment method for the user
    if club.use_last_payment_method_for_player_sessions:
        last_payment = (
            SessionEntry.objects.filter(system_number=system_number)
            .order_by("pk")
            .last()
        )
        if last_payment and last_payment.payment_method.payment_method != "IOU":
            payment_method = last_payment.payment_method

    # create session entry
    session_entry = SessionEntry(
        session=session,
        pair_team_number=table,
        seat=direction,
        system_number=system_number,
        payment_method=payment_method,
        player_name_from_file=player_file_name,
    )

    # set sitout or director to zero fee and paid
    if session_entry.system_number in [SITOUT, PLAYING_DIRECTOR]:
        session_entry.fee = 0
        session_entry.is_paid = True

    try:
        session_entry.save()

    except IntegrityError as err:
        return f"Invalid data found on line {line_no}. {err}."

    # Add additional session payments if set
    if session.additional_session_fee > 0:
        SessionMiscPayment(
            session_entry=session_entry,
            description=session.additional_session_fee_reason,
            amount=session.additional_session_fee,
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
                    system_number=-1,
                    fee=0,
                ).save()
