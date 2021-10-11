""" Club Menu Decorators to simplify code """
from django.http import HttpResponse
from django.shortcuts import redirect, get_object_or_404

from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden
from .models import Organisation
from .views.general import get_rbac_model_for_state


def check_club_menu_access(check_members=False):
    """checks if user should have access to a club menu

    Call as:

    from .decorators import check_club_menu_access

    @check_club_menu_access()
    def my_func(request, club):

    You don't need @login_required as it does that for you as well

    Optional parameters:

        check_members: Will also check for the role orgs.members.{club.id}.edit

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
            # kwargs.pop("club")

            # We only accept POSTs
            if request.method != "POST":
                return HttpResponse("Error - POST expected")

            # Get club
            club_id = request.POST.get("club_id")
            club = get_object_or_404(Organisation, pk=club_id)

            # Check for club level access - most common
            club_role = f"orgs.org.{club.id}.edit"
            if rbac_user_has_role(request.user, club_role):
                return function(request, club, *args, **kwargs)

            # Check for optional club parameter
            if check_members:
                member_role = f"orgs.members.{club.id}.edit"
                if rbac_user_has_role(request.user, member_role):
                    return function(request, club, *args, **kwargs)

            # Check for state level access
            rbac_model_for_state = get_rbac_model_for_state(club.state)
            state_role = "orgs.state.%s.edit" % rbac_model_for_state
            if rbac_user_has_role(request.user, state_role):
                return function(request, club, *args, **kwargs)

            # Check for global role
            if rbac_user_has_role(request.user, "orgs.admin.edit"):
                return function(request, club, *args, **kwargs)

            return rbac_forbidden(request, club_role)

        return _arguments_wrapper

    return _method_wrapper
