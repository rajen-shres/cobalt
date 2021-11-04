from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from organisations.models import Organisation, OrgVenue

from rbac.views import rbac_forbidden
from rbac.core import rbac_user_has_role
from .decorators import user_is_club_director

from ..forms import SessionForm
from ..models import Session


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
        "club_sessions/new_session.html",
        {
            "club": club,
            "session_form": session_form,
            "director_name": director_name,
            "new_or_edit": "new",
        },
    )


# @user_is_club_director()
@login_required()
def manage_session(request, session_id):
    """Main page to manage a club session after it has been created"""

    session = get_object_or_404(Session, pk=session_id)

    club = get_object_or_404(Organisation, pk=session.session_type.organisation.id)

    club_role = f"club_sessions.sessions.{club.id}.edit"
    if not rbac_user_has_role(request.user, club_role):
        return rbac_forbidden(request, club_role)

    return render(
        request, "club_sessions/manage_session.html", {"club": club, "session": session}
    )
