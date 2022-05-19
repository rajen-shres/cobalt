import codecs
import csv

from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from accounts.models import User, UnregisteredUser
from organisations.models import Organisation, OrgVenue

from rbac.views import rbac_forbidden
from rbac.core import rbac_user_has_role
from .decorators import user_is_club_director

from ..forms import SessionForm, FileImportForm
from ..models import Session, SessionEntry


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


@user_is_club_director()
def tab_session_htmx(request, club, session):
    """present the main session tab for the director"""

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

    # Get membership fees

    # Now add the object to the session list, also add colours for alternate tables
    for session_entry in session_entries:
        if session_entry.system_number in mixed_dict:
            session_entry.player = mixed_dict[session_entry.system_number]
            # table
            if session_entry.pair_team_number % 2 == 0:
                session_entry.table_colour = "even"
            else:
                session_entry.table_colour = "odd"
        else:
            # table colour - highlight if not a known player
            session_entry.table_colour = "unknown player"

    return render(
        request,
        "club_sessions/manage/session_htmx.html",
        {"session": session, "session_entries": session_entries},
    )


@user_is_club_director()
def tab_import_htmx(request, club, session):
    """file upload tab"""

    return render(
        request,
        "club_sessions/manage/import_htmx.html",
        {"session": session, "club": club},
    )


@user_is_club_director()
def import_file_upload_htmx(request, club, session):
    """Upload player names for a session"""

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

        # process data
        for line in csv_data:
            print(line)
            table = line[0]
            direction = line[1]
            system_number = int(line[2])
            SessionEntry(
                session=session,
                pair_team_number=table,
                seat=direction,
                system_number=system_number,
                amount_paid=0,
            ).save()
    else:
        print(form.errors)

    return HttpResponse("file thing")
