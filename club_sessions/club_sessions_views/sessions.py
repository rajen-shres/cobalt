from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from organisations.models import Organisation, OrgVenue

from rbac.views import rbac_forbidden
from rbac.core import rbac_user_has_role
from .decorators import user_is_club_director


#@user_is_club_director()
from ..forms import SessionForm


@login_required()
def new_session(request, club_id):
    """Set up a new bridge session for a club"""

    club=get_object_or_404(Organisation, pk=club_id)

    club_role = f"club_sessions.sessions.{club.id}.edit"
    if not rbac_user_has_role(request.user, club_role):
        return rbac_forbidden(request, club_role)

    # Set up form values
    director_name = request.user.full_name

    session_form = SessionForm(club=club, initial={"director": request.user})

    return render(request, "club_sessions/session.html", {"club": club, "session_form": session_form, "director_name": director_name})