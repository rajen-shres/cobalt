""" Club Menu Decorators to simplify code """
from django.http import HttpResponse
from django.shortcuts import redirect, get_object_or_404

from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden
from .models import Organisation
from .views.general import get_rbac_model_for_state


def _check_extra_role(request, function, club, extra_role, *args, **kwargs):
    """sub function to check for extra access"""

    if rbac_user_has_role(request.user, extra_role):
        return function(request, club, *args, **kwargs)
    else:
        return rbac_forbidden(request, extra_role)


def check_club_menu_access(
    check_members=False,
    check_comms=False,
    check_sessions=False,
    check_payments=False,
    check_org_edit=False,
):
    """checks if user should have access to a club menu

    Call as:

    from .decorators import check_club_menu_access

    @check_club_menu_access()
    def my_func(request, club):

    You don't need @login_required as it does that for you as well

    Optional parameters:

        check_members: Will also check for the role orgs.members.{club.id}.edit
        check_comms: Will also check for the role notifications.orgcomms.{club.id}.edit
        check_sessions: Will also check for the role club_sessions.sessions.{club.id}.edit
        check_payments: Will also check for the role payments.manage.{club.id}.edit
        check_org_edit: Will also check for the role orgs.org.{club.id}.edit

    We add a parameter (club) to the actual call which is fine for calls from
    URLs but if we call this internally it will need to be called without the
    club parameter.

    The optional parameters are only applied for normal admin users, Global or State
    admins get in anyway even if they don't have the extra permissions.

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

            # TODO: add a multiple option to RBAC so we can combine these into a single query

            # Check for state level access
            rbac_model_for_state = get_rbac_model_for_state(club.state)
            state_role = "orgs.state.%s.edit" % rbac_model_for_state
            if rbac_user_has_role(request.user, state_role):
                return function(request, club, *args, **kwargs)

            # Check for global role
            if rbac_user_has_role(request.user, "orgs.admin.edit"):
                return function(request, club, *args, **kwargs)

            # Check for club level access
            club_role = f"orgs.org.{club.id}.view"
            if rbac_user_has_role(request.user, club_role):

                # Check for optional member parameter
                if check_members:
                    extra_role = f"orgs.members.{club.id}.edit"
                    return _check_extra_role(
                        request, function, club, extra_role, *args, **kwargs
                    )

                # Check for optional comms parameter
                if check_comms:
                    extra_role = f"notifications.orgcomms.{club.id}.edit"
                    return _check_extra_role(
                        request, function, club, extra_role, *args, **kwargs
                    )

                # Check for optional sessions parameter
                if check_sessions:
                    extra_role = f"club_sessions.sessions.{club.id}.edit"
                    return _check_extra_role(
                        request, function, club, extra_role, *args, **kwargs
                    )

                # Check for optional sessions parameter
                if check_payments:
                    extra_role = f"payments.manage.{club.id}.edit"
                    return _check_extra_role(
                        request, function, club, extra_role, *args, **kwargs
                    )

                # Check for optional sessions parameter
                if check_org_edit:
                    extra_role = f"orgs.org.{club.id}.edit"
                    return _check_extra_role(
                        request, function, club, extra_role, *args, **kwargs
                    )

                # Passed the access check and there are no additional checks so all good
                return function(request, club, *args, **kwargs)

            return rbac_forbidden(request, club_role)

        return _arguments_wrapper

    return _method_wrapper
