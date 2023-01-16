""" Events Decorators to simplify code """
from django.http import HttpResponse
from django.shortcuts import redirect, get_object_or_404

from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden
from events.models import Congress


def check_convener_access():
    """checks if user is a convener for this congress

    Call as:

    from .decorators import check_convener_access

    @check_club_menu_access()
    def my_func(request, congress):

    You don't need @login_required as it does that for you as well

    We add a parameter (convener) to the actual call which is fine for calls from
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

            # We only accept POSTs
            if request.method != "POST":
                return HttpResponse("Error - POST expected")

            # Get congress
            congress_id = request.POST.get("congress_id")
            congress = get_object_or_404(Congress, pk=congress_id)

            # Check for global role
            if rbac_user_has_role(request.user, "orgs.admin.edit"):
                return function(request, congress, *args, **kwargs)

            # Check for club level access
            congress_role = f"events.org.{congress.congress_master.org.id}.edit"
            if rbac_user_has_role(request.user, congress_role):
                return function(request, congress, *args, **kwargs)

            return rbac_forbidden(request, congress_role, htmx=True)

        return _arguments_wrapper

    return _method_wrapper
