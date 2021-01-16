""" This module implements the login function. This is customised to allow
    users to login using either their email address or system_number.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from logs.views import log_event


class CobaltBackend(ModelBackend):
    """ Custom backend to control user logins. """

    def authenticate(
        self, request, username=None, password=None
    ):  # pylint: disable=arguments-differ
        """ method to authenticate users """

        user_model = get_user_model()  # get the user model from the system

        # Try email address, then username, then system_number

        con_type = None  # default is we don't know how they are connecting

        user = user_model.objects.filter(email=username).first()
        if user:
            con_type = "email"  # matched on email address
        else:
            try:
                user = user_model.objects.get(username=username)
                con_type = "username"  # matched on username
            except user_model.DoesNotExist:
                user = None

        if user is None:
            log_event(
                request=request,
                user="Login",
                severity="WARN",
                source="Accounts",
                sub_source="Login",
                message="Login failed - unknown userid",
            )
            return None

        # we have a matching user - try to login

        if user.check_password(password):
            log_event(
                request=request,
                user=user.full_name,
                severity="INFO",
                source="Accounts",
                sub_source="Login",
                message="Logged in using %s" % con_type,
            )
            return user

        else:
            log_event(
                request=request,
                user="login",
                severity="INFO",
                source="Accounts",
                sub_source="Login",
                message="Login failed for %s - incorrect password" % username,
            )

            return None
