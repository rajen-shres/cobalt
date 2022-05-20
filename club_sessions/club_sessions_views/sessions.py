import codecs
import csv

from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from accounts.models import User, UnregisteredUser
from cobalt.settings import BRIDGE_CREDITS
from organisations.models import Organisation, OrgVenue
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
        mixed_dict[user.system_number] = user

    # Add unregistered to dictionary
    for un_reg in un_regs:
        un_reg.is_un_reg = True
        mixed_dict[un_reg.system_number] = un_reg

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
    """Sub of tab_Session_htmx. Adds extra values to the session_entries for display by the template"""

    # Now add the object to the session list, also add colours for alternate tables
    for session_entry in session_entries:

        # Add User or UnregisterUser to the entry
        if session_entry.system_number in mixed_dict:
            session_entry.player = mixed_dict[session_entry.system_number]

        # table
        if session_entry.pair_team_number % 2 == 0:
            session_entry.table_colour = "even"
        else:
            session_entry.table_colour = "odd"

        # membership
        if session_entry.system_number in membership_type_dict:
            session_entry.membership = membership_type_dict[session_entry.system_number]
        else:
            session_entry.membership = "Guest"

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
        {"session": session, "session_entries": session_entries},
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


@user_is_club_director()
def import_file_upload_htmx(request, club, session):
    """Upload player names for a session"""

    messages = []

    form = FileImportForm(request.POST, request.FILES)
    if form.is_valid():
        # TODO: Might not want to do this
        SessionEntry.objects.filter(session=session).delete()

        # TODO: This isn't the proper format for the input file - change later
        csv_file = request.FILES["file"]

        # get CSV reader (convert bytes to strings)
        csv_data = csv.reader(codecs.iterdecode(csv_file, "utf-8"))

        # skip header
        next(csv_data, None)

        # process file
        for line_no, line in enumerate(csv_data, start=2):
            response = _import_file_upload_htmx_process_line(
                line, line_no, session, club
            )
            if response:
                messages.append(response)

        _import_file_upload_htmx_fill_in_table_gaps(session)

    else:
        print(form.errors)

    # Tell the parent function that the button was pressed
    reload = True

    return tab_import_htmx(request, messages=messages, reload=reload)


def _import_file_upload_htmx_process_line(line, line_no, session, club):
    """Process a single line from the import file"""

    # Extract data
    try:
        table = line[0]
        direction = line[1]
        system_number = int(line[2])
    except ValueError:
        return f"Invalid data found on line {line_no}. Ignored."

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
