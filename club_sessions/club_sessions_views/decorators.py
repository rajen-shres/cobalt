""" Club sessions Decorators to simplify code """
from django.http import HttpResponse
from django.shortcuts import redirect, get_object_or_404

from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden

from organisations.models import Organisation


def user_is_club_director():
    """checks if user is a director for this club. Requires Request to have a club_id parameter

    Call as:

    from .decorators import user_is_club_director

    @user_is_club_director()
    def my_func(request, club):

    You don't need @login_required as it does that for you as well

    We add a parameter (club) to the actual call which is fine for calls from
    URLs but if we call this internally it will need to be called without the
    club parameter.

    """

    # Need two layers of wrapper to handle the parameters being passed in
    def _method_wrapper(function):

        # second layer
        def _arguments_wrapper(request, *args, **kwargs):

            # Test if logged in
            if not request.user.is_authenticated:
                return redirect("/")

            # pop the club parameter if present. This allows us to call this directly within the code
            # Its a hack but it is very confusing to have the IDE complain about the missing parameter
            try:
                kwargs.pop("club")
            except KeyError:
                pass

            # We only accept POSTs
            if request.method != "POST":
                return HttpResponse("Error - POST expected")

            # Get club
            club_id = request.POST.get("club_id")
            club = get_object_or_404(Organisation, pk=club_id)

            # Check for access
            club_role = f"club_sessions.sessions.{club.id}.edit"
            if rbac_user_has_role(request.user, club_role):
                return function(request, club, *args, **kwargs)

            return rbac_forbidden(request, club_role)

        return _arguments_wrapper

    return _method_wrapper
