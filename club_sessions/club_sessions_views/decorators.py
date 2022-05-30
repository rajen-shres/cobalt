""" Club sessions Decorators to simplify code """
from django.http import HttpResponse
from django.shortcuts import redirect, get_object_or_404

from club_sessions.models import Session, SessionEntry
from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden

from organisations.models import Organisation


def user_is_club_director(include_session_entry=False):
    """checks if user is a director for this club. Requires Request to have a club_id parameter

    Call as:

    from .decorators import user_is_club_director

    @user_is_club_director()
    def my_func(request, club):

    You don't need @login_required as it does that for you as well

    We add a parameter (club) to the actual call which is fine for calls from
    URLs but if we call this internally it will need to be called without the
    club parameter.

    We also add session.

    Optionally, specify include_session_entry to have that loaded and checked for validity

    """

    # Need two layers of wrapper to handle the parameters being passed in
    def _method_wrapper(function):

        # second layer
        def _arguments_wrapper(request, *args, **kwargs):

            # Test if logged in
            if not request.user.is_authenticated:
                return redirect("/")

            # We only accept POSTs
            if request.method != "POST":
                return HttpResponse("Error - POST expected")

            # Get club
            club_id = request.POST.get("club_id")
            club = get_object_or_404(Organisation, pk=club_id)

            # Get session
            session_id = request.POST.get("session_id")
            session = get_object_or_404(Session, pk=session_id)

            # Check for access
            club_role = f"club_sessions.sessions.{club.id}.edit"
            if (
                rbac_user_has_role(request.user, club_role)
                and session.session_type.organisation == club
            ):
                # optionally, check for session_entry
                if not include_session_entry:
                    # check not required, return
                    return function(request, club, session, *args, **kwargs)

                # get session_entry
                session_entry_id = request.POST.get("session_entry_id")
                session_entry = get_object_or_404(SessionEntry, pk=session_entry_id)

                # check session entry is for this session, and include session_entry in function call
                if session_entry.session == session:
                    return function(
                        request, club, session, session_entry, *args, **kwargs
                    )

            return rbac_forbidden(request, club_role)

        return _arguments_wrapper

    return _method_wrapper
