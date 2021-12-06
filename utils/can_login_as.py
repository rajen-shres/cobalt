from logs.views import log_event


def check(request, target):
    """

    We use django-loginas to control admins taking over user sessions.
    This function validates and logs actions.

    Note: we only get an event for a user becoming another user, not for any actions they
    perform as that user.

    """

    if request.user.is_superuser:
        log_event(
            user=request.user,
            severity="HIGH",
            source="Accounts",
            sub_source="Login-as-user",
            message=f"Logged in as {target}",
            request=request,
        )
        return True

    return False
