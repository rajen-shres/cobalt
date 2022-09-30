from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from club_sessions.forms import SessionForm
from organisations.models import Organisation
from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden


@login_required()
def new_session(request, club_id):
    """Set up a new bridge session for a club. Normally we import a file, so this won't be used much."""

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
        session = session_form.save(commit=False)
        session.club = club
        session.save()
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
