import codecs
import csv
import re

from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from accounts.accounts_views.core import (
    add_un_registered_user_with_mpc_data,
    get_user_or_unregistered_user_from_system_number,
)
from accounts.models import User, UnregisteredUser
from cobalt.settings import BRIDGE_CREDITS, GLOBAL_CURRENCY_SYMBOL
from masterpoints.views import abf_checksum_is_valid
from notifications.notifications_views.core import (
    send_cobalt_email_to_system_number,
)
from organisations.models import (
    Organisation,
    ClubLog,
    MemberMembershipType,
    MiscPayType,
)
from organisations.views.general import get_membership_type_for_players
from payments.models import OrgPaymentMethod, MemberTransaction, UserPendingPayment
from payments.payments_views.payments_api import payment_api_batch

from rbac.views import rbac_forbidden
from rbac.core import rbac_user_has_role
from .decorators import user_is_club_director

from ..forms import SessionForm, FileImportForm, UserSessionForm
from ..models import (
    Session,
    SessionEntry,
    SessionTypePaymentMethodMembership,
    SessionMiscPayment,
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

    has_session_entries = SessionEntry.objects.filter(session=session).exists()

    return render(
        request,
        "club_sessions/manage/manage_session.html",
        {"club": club, "session": session, "has_session_entries": has_session_entries},
    )


@user_is_club_director()
def tab_settings_htmx(request, club, session):
    """Edit fields that were set up when the session was started"""

    message = ""

    if "save_settings" in request.POST:
        session_form = SessionForm(request.POST, club=club, instance=session)
        if session_form.is_valid():
            session = session_form.save()
            message = "Session Updated"
        else:
            print(session_form.errors)

    session_form = SessionForm(club=club, instance=session)

    director_name = f"{session.director}"

    return render(
        request,
        "club_sessions/manage/settings_htmx.html",
        {
            "session_form": session_form,
            "club": club,
            "session": session,
            "message": message,
            "director_name": director_name,
        },
    )


def _load_session_entry_static(session, club):
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
        mixed_dict[user.system_number] = {
            "type": "User",
            "value": user,
            "icon": "account_circle",
        }

    # Add unregistered to dictionary
    for un_reg in un_regs:
        un_reg.is_un_reg = True
        mixed_dict[un_reg.system_number] = {
            "type": "UnregisteredUser",
            "value": un_reg,
            "icon": "stars",
        }

    # Get memberships
    membership_type_dict = get_membership_type_for_players(system_number_list, club)

    # Load session fees
    session_fees = _get_session_fees_for_club(club)

    return session_entries, mixed_dict, session_fees, membership_type_dict


def _get_session_fees_for_club(club):
    """return session fees as a dictionary. We use the name of the membership as the key, not the number

    e.g. session_fees = {"Standard": {"EFTPOS": 5, "Cash": 12}}

    """

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

    return session_fees


def _augment_session_entries(
    session_entries, mixed_dict, membership_type_dict, session_fees, club
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

    # The payment method may no longer be valid, we want to flag this
    valid_payment_methods = OrgPaymentMethod.objects.filter(
        organisation=club, active=True
    ).values_list("payment_method", flat=True)

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
            session_entry.icon = mixed_dict[session_entry.system_number]["icon"]
            icon_text = f"{session_entry.player.first_name} is "
        else:
            session_entry.player_type = "NotRegistered"
            session_entry.icon = "error"
            session_entry.player = {"full_name": "Unknown"}
            icon_text = "This person is "

        # membership
        if session_entry.system_number in membership_type_dict:
            # This person is a member
            session_entry.membership = membership_type_dict[session_entry.system_number]
            session_entry.membership_type = "member"
            session_entry.icon_colour = "primary"
            icon_text += f"a {session_entry.membership} member."
        else:
            # Not a member
            session_entry.membership = "Guest"
            icon_text += "a Guest."
            if session_entry.system_number >= 0 and abf_checksum_is_valid(
                session_entry.system_number
            ):
                session_entry.membership_type = "Valid Number"
                session_entry.icon_colour = "warning"
            else:
                session_entry.membership_type = "Invalid Number"
                session_entry.icon_colour = "dark"

        # valid payment method. In list of valid is fine, or simple not set is fine too
        if session_entry.payment_method:
            session_entry.payment_method_is_valid = (
                session_entry.payment_method.payment_method in valid_payment_methods
            )
        else:
            session_entry.payment_method_is_valid = True

        # Add icon text
        session_entry.icon_text = icon_text

    # work out payment method and if user has sufficient funds
    return _calculate_payment_method_and_balance(session_entries, session_fees, club)


def _calculate_payment_method_and_balance(session_entries, session_fees, club):
    """work out who can pay by bridge credits and if they have enough money"""

    # First build list of users who are bridge credit eligible
    bridge_credit_users = [
        session_entry.system_number
        for session_entry in session_entries
        if session_entry.player_type == "User"
    ]

    # Now get their balances
    balances = {
        member_transaction.member: member_transaction.balance
        for member_transaction in MemberTransaction.objects.filter(
            member__system_number__in=bridge_credit_users
        )
    }

    bridge_credit_payment_method = OrgPaymentMethod.objects.filter(
        organisation=club, payment_method=BRIDGE_CREDITS, active=True
    ).first()

    # Go through and add balance to session entries
    for session_entry in session_entries:
        if session_entry.player_type == "User":
            # if not in balances then it is zero
            session_entry.balance = balances.get(session_entry.player, 0)

            # Only change payment method to Bridge Credits if not set to something already
            if not session_entry.payment_method:
                session_entry.payment_method = bridge_credit_payment_method

        # fee due
        if session_entry.payment_method and not session_entry.fee:
            session_entry.fee = session_fees[session_entry.membership][
                session_entry.payment_method.payment_method
            ]

        session_entry.save()

    return session_entries


@user_is_club_director()
def tab_session_htmx(request, club, session, message=""):
    """present the main session tab for the director"""

    # load static
    (
        session_entries,
        mixed_dict,
        session_fees,
        membership_type_dict,
    ) = _load_session_entry_static(session, club)

    # augment the session_entries
    session_entries = _augment_session_entries(
        session_entries, mixed_dict, membership_type_dict, session_fees, club
    )

    # get payment methods for this club
    payment_methods = OrgPaymentMethod.objects.filter(organisation=club, active=True)

    return render(
        request,
        "club_sessions/manage/session_htmx.html",
        {
            "club": club,
            "session": session,
            "session_entries": session_entries,
            "payment_methods": payment_methods,
            "message": message,
        },
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


def _edit_session_entry_handle_post(request, club, session_entry):
    """Sub for edit_session_entry_htmx to handle the form being posted"""

    form = UserSessionForm(request.POST, club=club, session_entry=session_entry)
    if not form.is_valid():
        print(form.errors)
        return form, "There were errors on the form"

    # get user type
    is_user = request.POST.get("is_user")
    is_un_reg = request.POST.get("is_un_reg")

    # Handle session data
    session_entry.fee = form.cleaned_data["fee"]
    session_entry.amount_paid = form.cleaned_data["amount_paid"]
    payment_method = OrgPaymentMethod.objects.get(
        pk=form.cleaned_data["payment_method"]
    )

    # Handle player being changed
    new_user_id = form.cleaned_data["player_no"]
    system_number = None
    if new_user_id:
        if is_user:
            system_number = User.objects.get(pk=new_user_id).system_number
        elif is_un_reg:
            system_number = UnregisteredUser.objects.get(pk=new_user_id).system_number
    if system_number:
        session_entry.system_number = system_number

    # Handle IOUs
    if "payment_method" in form.changed_data:
        _handle_iou_changes(payment_method, club, session_entry, request.user)

    session_entry.payment_method = payment_method
    session_entry.save()

    return form, "Data saved"


def _handle_iou_changes(payment_method, club, session_entry, administrator):
    """handle the payment type toggling between IOU and something else"""

    # Check for turning on
    if payment_method.payment_method == "IOU":
        # For safety ensure we don't duplicate
        user_pending_payment, _ = UserPendingPayment.objects.get_or_create(
            organisation=club,
            system_number=session_entry.system_number,
            session_entry=session_entry,
            amount=session_entry.fee,
            description=session_entry.session.description,
        )
        user_pending_payment.save()

        subject = f"Pending Payment to {club}"
        message = f"""
        {administrator.full_name} has recorded you as entering {session_entry.session} but not paying.
        That is fine, you can pay later.
        <br><br>
        The amount owing is {GLOBAL_CURRENCY_SYMBOL}{session_entry.fee}.
        <br><br>
        If you believe this to be incorrect please contact {club} directly in the first instance.
        """

        send_cobalt_email_to_system_number(
            session_entry.system_number,
            subject,
            message,
            club=club,
            administrator=administrator,
        )

    # Check for turning off
    if session_entry.payment_method.payment_method == "IOU":
        UserPendingPayment.objects.filter(
            organisation=club,
            system_number=session_entry.system_number,
            session_entry=session_entry,
        ).delete()


@user_is_club_director(include_session_entry=True)
def edit_session_entry_htmx(request, club, session, session_entry):
    """Edit a single session_entry on the session page"""

    # We hide a lot of extra things in the form for this view

    # See if POSTed form or not
    if "save_session" in request.POST:
        form, message = _edit_session_entry_handle_post(request, club, session_entry)
    else:
        form = UserSessionForm(club=club, session_entry=session_entry)
        message = ""

    # Check if payment method used is still valid
    valid_payment_methods = [item[1] for item in form.fields["payment_method"].choices]

    # unset or in the list are both valid
    if session_entry.payment_method:
        payment_method_is_valid = (
            session_entry.payment_method.payment_method in valid_payment_methods
        )
    else:
        payment_method_is_valid = True

    return render(
        request,
        "club_sessions/manage/edit_session_entry_htmx.html",
        {
            "club": club,
            "session": session,
            "session_entry": session_entry,
            "form": form,
            "message": message,
            "payment_method_is_valid": payment_method_is_valid,
        },
    )


@user_is_club_director(include_session_entry=True)
def edit_session_entry_extras_htmx(request, club, session, session_entry, message=""):
    """Handle the extras part of the session entry edit screen - IOUs, misc payments etc"""

    # get this orgs miscellaneous payment types and payment methods
    misc_payment_types = MiscPayType.objects.filter(organisation=club)
    payment_methods = OrgPaymentMethod.objects.filter(active=True, organisation=club)

    # get misc payments for this user through the extended info table
    #    misc_payments_for_user =

    # Check for IOUs from any club
    user_pending_payments = UserPendingPayment.objects.filter(
        system_number=session_entry.system_number
    )

    # Get any existing misc payments for this session
    session_misc_payments = SessionMiscPayment.objects.filter(
        session_entry=session_entry
    )

    player = get_user_or_unregistered_user_from_system_number(
        session_entry.system_number
    )

    return render(
        request,
        "club_sessions/manage/edit_session_entry_extras_htmx.html",
        {
            "misc_payment_types": misc_payment_types,
            "payment_methods": payment_methods,
            "user_pending_payments": user_pending_payments,
            "session_entry": session_entry,
            "session": session,
            "player": player,
            "club": club,
            "session_misc_payments": session_misc_payments,
            "message": message,
        },
    )


@user_is_club_director(include_session_entry=True)
def change_payment_method_htmx(request, club, session, session_entry):
    """called when the payment method dropdown is changed on the session tab"""

    payment_method = get_object_or_404(
        OrgPaymentMethod, pk=request.POST.get("payment_method")
    )

    # IOU is a special case. Clubs can disable it, but if it is there we generate an IOU for the user
    _handle_iou_changes(payment_method, club, session_entry, request.user)

    # Get the membership_type for this user and club, None means they are a guest
    member_membership_type = (
        MemberMembershipType.objects.filter(system_number=session_entry.system_number)
        .filter(membership_type__organisation=club)
        .first()
    )

    if member_membership_type:
        member_membership = member_membership_type.membership_type
    else:
        member_membership = None  # Guest

    fee = SessionTypePaymentMethodMembership.objects.filter(
        session_type_payment_method__session_type__organisation=club,
        session_type_payment_method__payment_method=payment_method,
        membership=member_membership,
    ).first()

    session_entry.payment_method = payment_method
    session_entry.fee = fee.fee
    session_entry.save()

    return HttpResponse(fee.fee)


@user_is_club_director(include_session_entry=True)
def change_paid_amount_status_htmx(request, club, session, session_entry):
    """Change the status of the amount paid for a user. We simply toggle the paid amount from 0 to full amount"""

    # TODO: Handle bridge credits - what do we do if already paid and changed to another payment method?

    if session_entry.amount_paid == session_entry.fee:
        session_entry.amount_paid = 0
    else:
        session_entry.amount_paid = session_entry.fee or 0
    session_entry.save()

    return HttpResponse("")


def _session_totals_calculations(
    session, session_entries, session_fees, membership_type_dict
):
    """sub of session_totals_htmx to build dict of totals"""

    # initialise totals
    totals = {
        "tables": 0,
        "players": 0,
        "unknown_payment_methods": 0,
        "bridge_credits_due": 0,
        "bridge_credits_received": 0,
        "other_methods_due": 0,
        "other_methods_received": 0,
    }

    # go through entries and update totals
    for session_entry in session_entries:

        # ignore missing players and playing directors
        if session_entry.system_number in [-1, 0, 1]:
            continue

        totals["players"] += 1

        # handle unknown payment methods
        if not session_entry.payment_method:
            totals["unknown_payment_methods"] += 1
            continue

        # we only store system_number on the session_entry. Need to look up amount due via membership type for
        # this system number and the session_fees for this club for each membership type

        # It is also possible that the static data has changed since this was created, so we need to
        # handle the session_fees not existing for this payment_method

        # Get membership for user, if not found then this will be a Guest
        membership_for_this_user = membership_type_dict.get(
            session_entry.system_number, "Guest"
        )

        if session_entry.fee:
            # If fee is set then use that
            this_fee = session_entry.fee
        else:
            # Otherwise, try to look it up
            try:
                this_fee = session_fees[membership_for_this_user][
                    session_entry.payment_method.payment_method
                ]
            except KeyError:
                # if that fails default to 0 - will mean the static has changed since we set the payment_method
                # and this payment method is no longer in use. 0 seems a good default
                this_fee = 0

        # Update totals
        if session_entry.payment_method.payment_method == BRIDGE_CREDITS:
            totals["bridge_credits_due"] += this_fee
            totals["bridge_credits_received"] += session_entry.amount_paid
        else:
            totals["other_methods_due"] += this_fee
            totals["other_methods_received"] += session_entry.amount_paid

    totals["tables"] = totals["players"] / 4

    # Calculate overall status
    if session.is_complete:
        status = "Complete"
    elif totals["unknown_payment_methods"] == 0:
        status = "Ready"
    else:
        status = "Fix"

    return totals, status


@user_is_club_director()
def session_totals_htmx(request, club, session):
    """Calculate totals for a session and return formatted header over htmx. Repeats a lot of what
    happens for loading the session tab in the first place."""

    # load static
    (
        session_entries,
        mixed_dict,
        session_fees,
        membership_type_dict,
    ) = _load_session_entry_static(session, club)

    # augment the session_entries
    session_entries = _augment_session_entries(
        session_entries, mixed_dict, membership_type_dict, session_fees, club
    )

    # do calculations
    session_entries = _calculate_payment_method_and_balance(
        session_entries, session_fees, club
    )

    # calculate totals
    totals, status = _session_totals_calculations(
        session, session_entries, session_fees, membership_type_dict
    )

    return render(
        request,
        "club_sessions/manage/totals_htmx.html",
        {"totals": totals, "status": status},
    )


@user_is_club_director(include_session_entry=True)
def add_misc_payment_htmx(request, club, session, session_entry):
    """Adds a miscellaneous payment for a user in a session"""

    # TODO: Change this to use the optional_description and allow user to type value in

    # load data from form
    misc_payment = get_object_or_404(MiscPayType, pk=request.POST.get("misc_payment"))
    amount = float(request.POST.get("amount"))

    # validate
    if amount <= 0:
        return edit_session_entry_extras_htmx(
            request, message="Amount must be greater than zero"
        )

    # load member
    member = get_user_or_unregistered_user_from_system_number(
        session_entry.system_number
    )
    if not member:
        return edit_session_entry_extras_htmx(request, message="Error loading member")

    # Add misc payment
    SessionMiscPayment(
        session_entry=session_entry,
        optional_description=misc_payment.description,
        amount=amount,
    ).save()

    return edit_session_entry_extras_htmx(
        request, message=f"{misc_payment.description} added"
    )


@user_is_club_director()
def process_bridge_credits_htmx(request, club, session):
    """handle bridge credits for the session - called from a big button"""

    # Get bridge credits for this org
    bridge_credits = OrgPaymentMethod.objects.filter(
        active=True, organisation=club, payment_method="Bridge Credits"
    ).first()

    if not bridge_credits:
        return tab_session_htmx(
            request,
            message="Bridge Credits are not set up for this organisation. Add through Settings if you wish to use Bridge Credits",
        )

    # Get any extras
    extras_qs = (
        SessionMiscPayment.objects.filter(session_entry__session=session)
        .values("session_entry")
        .annotate(extras=Sum("amount"))
    )

    # convert to dict
    extras = {item["session_entry"]: float(item["extras"]) for item in extras_qs}
    print(extras)

    # For each player go through and work out what they owe
    session_entries = SessionEntry.objects.filter(
        session=session, amount_paid=0, payment_method=bridge_credits
    )
    system_numbers = session_entries.values_list("system_number", flat=True)
    users_qs = User.objects.filter(system_number__in=system_numbers)
    users_by_system_number = {user.system_number: user for user in users_qs}

    print(users_by_system_number)

    for session_entry in SessionEntry.objects.filter(
        session=session, amount_paid=0, payment_method=bridge_credits
    ):

        amount_paid = (
            float(session_entry.amount_paid) if session_entry.amount_paid else 0
        )
        fee = float(session_entry.fee) if session_entry.fee else 0
        amount = fee - amount_paid + extras.get(session_entry.id, 0)
        print(session_entry.system_number, amount)

        # Try payment
        member = users_by_system_number[session_entry.system_number]
        if payment_api_batch(
            member=member,
            description=f"{session}",
            amount=amount,
            organisation=club,
            payment_type="Club Payment",
            session=session,
        ):
            session_entry.amount_paid = session_entry.fee
            session_entry.save()

            SessionMiscPayment.objects.filter(
                session_entry__session=session,
                session_entry__system_number=session_entry.system_number,
            ).update(payment_made=True)

            # session_entry.amount_paid =

    return tab_session_htmx(request, message="Coming soon")


@user_is_club_director(include_session_entry=True)
def delete_misc_session_payment_htmx(request, club, session, session_entry):
    """Delete a misc session payment"""

    # Get data
    session_misc_payment = get_object_or_404(
        SessionMiscPayment, pk=request.POST.get("session_misc_payment_id")
    )

    # validate
    if session_misc_payment.session_entry != session_entry:
        return edit_session_entry_extras_htmx(
            request, message="Misc payment not for this session"
        )

    # handle already paid
    if session_misc_payment.payment_made:
        return edit_session_entry_extras_htmx(
            request, message="Payment already made. Handle later"
        )

    # delete
    session_misc_payment.delete()
    return edit_session_entry_extras_htmx(
        request, message="Miscellaneous payment deleted"
    )
