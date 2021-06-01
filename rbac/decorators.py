""" RBAC Decorators to simplify code """

from django.shortcuts import redirect
from .core import rbac_user_has_role
from .views import rbac_forbidden


def rbac_check_role(role1, role2=None):
    """checks if a users has a role, optionally checks against a second role as well, either will pass.

    Call as:

    from rbac.decorators import rbac_check_role

    @rbac_check_role("some_app.some_role")
    def my_func(request):

    OR

    @rbac_check_role("some_app.some_role", "some_role.some_other_role")
    def my_func(request):

    You don't need @login_required as it does that for you as well
    """

    # Need two layers of wrapper to handle the parameters being passed in
    def _method_wrapper(function):

        # second layer
        def _arguments_wrapper(request, *args, **kwargs):

            # Test if logged in
            if not request.user.is_authenticated:
                return redirect("/")

            # Test role1
            if rbac_user_has_role(request.user, role1):
                return function(request, *args, **kwargs)
            elif role2 and rbac_user_has_role(request.user, role2):
                return function(request, *args, **kwargs)

            else:
                return rbac_forbidden(request, role1)

        return _arguments_wrapper

    return _method_wrapper
