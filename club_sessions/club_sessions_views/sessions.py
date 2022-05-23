import codecs
import csv
import re

from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from accounts.accounts_views.core import add_un_registered_user_with_mpc_data
from accounts.models import User, UnregisteredUser
from cobalt.settings import BRIDGE_CREDITS
from masterpoints.views import abf_checksum_is_valid
from organisations.models import Organisation, OrgVenue, ClubLog
from organisations.views.general import get_membership_type_for_players
from payments.models import OrgPaymentMethod

from rbac.views import rbac_forbidden
from rbac.core import rbac_user_has_role
from .decorators import user_is_club_director

from ..forms import SessionForm, FileImportForm
from ..models import (
    Session,
    SessionEntry,
    SessionTypePaymentMethodMembership,
    SessionTypePaymentMethod,
)


@login_required()
def new_session(request, club_id):
    """Set up a new bridge session for a club"""

    club = get_object_or_404(Organisation, pk=club_id)

    club_role = f"club_sessions.sessions.{club.id}.edit"
    if not rbac_user_has_role(request.user, club_role):
        return rbac_forbidden(request, club_role)

    # Set up form values
    director_name = request.user.full_name

    # Load form
    session_form = SessionForm(
        request.POST or None, club=club, initial={"director": request.user}
    )

    if request.method == "POST" and session_form.is_valid():
        session = session_form.save()
        return redirect("club_sessions:manage_session", session_id=session.id)
    else:
        print(session_form.errors)

    return render(
        request,
        "club_sessions/new/new_session.html",
        {
            "club": club,
            "session_form": session_form,
            "director_name": director_name,
            "new_or_edit": "new",
        },
    )


@login_required()
def manage_session(request, session_id):
    """Main page to manage a club session after it has been created"""

    session = get_object_or_404(Session, pk=session_id)

    club = get_object_or_404(Organisation, pk=session.session_type.organisation.id)

    club_role = f"club_sessions.sessions.{club.id}.edit"
    if not rbac_user_has_role(request.user, club_role):
        return rbac_forbidden(request, club_role)

    return render(
        request,
        "club_sessions/manage/manage_session.html",
        {"club": club, "session": session},
    )


@user_is_club_director()
def tab_settings_htmx(request, club, session):
    """Edit fields that were set up when the session was started"""

    if "save_settings" in request.POST:
        session_form = SessionForm(request.POST, club=club, instance=session)
        if session_form.is_valid():
            session = session_form.save()

    else:
        session_form = SessionForm(club=club)

    return render(
        request,
        "club_sessions/manage/settings_htmx.html",
        {"session_form": session_form, "club": club, "session": session},
    )


def _tab_session_htmx_load_static(session, club):
    """Sub of tab_session_htmx. Load the data we need to be able to process the session tab"""

    # Get the entries for this session
    session_entries = SessionEntry.objects.filter(session=session)

    # Map to Users or UnregisteredUsers

    # Get system numbers
    system_number_list = session_entries.values_list("system_number")

    # Get Users and UnregisteredUsers
    users = User.objects.filter(system_number__in=system_number_list)
    un_regs = UnregisteredUser.objects.filter(system_number__in=system_number_list)

    # Convert to a dictionary
    mixed_dict = {}

    for user in users:
        user.is_user = True
        mixed_dict[user.system_number] = {"type": "User", "value": user}

    # Add unregistered to dictionary
    for un_reg in un_regs:
        un_reg.is_un_reg = True
        mixed_dict[un_reg.system_number] = {"type": "UnregisteredUser", "value": un_reg}

    # Get memberships
    membership_type_dict = get_membership_type_for_players(system_number_list, club)

    # Load session fees and turn into a dictionary
    fees = SessionTypePaymentMethodMembership.objects.filter(
        session_type_payment_method__session_type__organisation=club
    ).filter()

    session_fees = {}
    for fee in fees:
        membership_name = "Guest" if fee.membership is None else fee.membership.name
        if membership_name not in session_fees:
            session_fees[membership_name] = {}
        session_fees[membership_name][
            fee.session_type_payment_method.payment_method.payment_method
        ] = fee.fee

    return session_entries, mixed_dict, session_fees, membership_type_dict


def _tab_session_htmx_augment_session_entries(
    session_entries, mixed_dict, membership_type_dict, session_fees
):
    """Sub of tab_Session_htmx. Adds extra values to the session_entries for display by the template

    Players can be:
        Users
        UnregisteredUsers
        Nothing

        If Nothing, they can have a valid ABF number, an invalid ABF number or no ABF number

    Their relationship with the club can be:
        Member
        Non-member

    """

    # Now add the object to the session list, also add colours for alternate tables
    for session_entry in session_entries:

        # table
        if session_entry.pair_team_number % 2 == 0:
            session_entry.table_colour = "even"
        else:
            session_entry.table_colour = "odd"

        # Add User or UnregisterUser to the entry and note the player_type
        if session_entry.system_number in mixed_dict:
            session_entry.player = mixed_dict[session_entry.system_number]["value"]
            session_entry.player_type = mixed_dict[session_entry.system_number]["type"]
        else:
            session_entry.player_type = "NotRegistered"

        # membership
        if session_entry.system_number in membership_type_dict:
            session_entry.membership = membership_type_dict[session_entry.system_number]
            session_entry.membership_type = "member"
        else:
            session_entry.membership = "Guest"
            if session_entry.system_number >= 0 and abf_checksum_is_valid(
                session_entry.system_number
            ):
                session_entry.membership_type = "Valid Number"
            else:
                session_entry.membership_type = "Invalid Number"

        # fee due
        if session_entry.payment_method:
            session_entry.fee = session_fees[session_entry.membership][
                session_entry.payment_method.payment_method
            ]

    return session_entries


@user_is_club_director()
def tab_session_htmx(request, club, session):
    """present the main session tab for the director"""

    # load static
    (
        session_entries,
        mixed_dict,
        session_fees,
        membership_type_dict,
    ) = _tab_session_htmx_load_static(session, club)

    # augment the session_entries
    session_entries = _tab_session_htmx_augment_session_entries(
        session_entries, mixed_dict, membership_type_dict, session_fees
    )

    return render(
        request,
        "club_sessions/manage/session_htmx.html",
        {"club": club, "session": session, "session_entries": session_entries},
    )


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

    for line in text_file.readlines():
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

        try:
            table = int(parts[0])
            player1, player2 = re.findall(r"\d+", parts[1])
        except ValueError:
            continue

        for direction in current_direction:

            response = _import_file_upload_htmx_process_line(
                [table, direction, player1], line_no, session, club, request
            )
            if response:
                messages.append(response)

    return messages


@user_is_club_director()
def import_file_upload_htmx(request, club, session):
    """Upload player names for a session"""

    messages = []

    form = FileImportForm(request.POST, request.FILES)
    if form.is_valid():

        SessionEntry.objects.filter(session=session).delete()

        if "generic_csv" in request.POST:
            _import_file_upload_htmx_simple_csv(request, club, session)
        elif "compscore2" in request.POST:
            _import_file_upload_htmx_compscore2(request, club, session)

        _import_file_upload_htmx_fill_in_table_gaps(session)

    else:
        print(form.errors)

    # Tell the parent function that the button was pressed
    reload = True

    return tab_import_htmx(request, messages=messages, reload=reload)


def _import_file_upload_htmx_process_line(line, line_no, session, club, request):
    """Process a single line from the import file"""

    # Extract data
    try:
        table = line[0]
        direction = line[1]
        system_number = int(line[2])
    except ValueError:
        return f"Invalid data found on line {line_no}. Ignored."

    # If this user isn't registered then add them from the MPC
    if not UnregisteredUser.objects.filter(system_number=system_number).exists():
        response = add_un_registered_user_with_mpc_data(
            system_number, club, request.user
        )
        print(response)
        # if response:
        # ClubLog(
        #     organisation=club,
        #     actor=request.user,
        #     action=f"Added un-registered user {form.cleaned_data['first_name']} {form.cleaned_data['last_name']}",
        # ).save()

    # Work out the payment method to use - can be changed by the director
    registered_user = User.objects.filter(system_number=system_number).first()

    payment_method = None
    if registered_user:
        payment_method = OrgPaymentMethod.objects.filter(
            organisation=club, payment_method=BRIDGE_CREDITS
        ).first()

    # create session entry
    SessionEntry(
        session=session,
        pair_team_number=table,
        seat=direction,
        system_number=system_number,
        amount_paid=0,
        payment_method=payment_method,
    ).save()

    return None


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


@user_is_club_director()
def edit_session_entry_htmx(request, club, session):
    """Edit a single session_entry on the session page and return the whole tab if we change anything"""

    session_entry = get_object_or_404(
        SessionEntry, pk=request.POST.get("session_entry_id")
    )

    if session_entry.session != session:
        return HttpResponse("Access Denied")

    if "save_session" not in request.POST:

        # Try to load member
        member = User.objects.filter(system_number=session_entry.system_number).first()

        return render(
            request,
            "club_sessions/manage/edit_session_entry_htmx.html",
            {
                "club": club,
                "session": session,
                "session_entry": session_entry,
                "member": member,
            },
        )

    return HttpResponse("edit it")
