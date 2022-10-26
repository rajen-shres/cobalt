""" This middleware checks for the presence of an environment variable that puts the
    site into maintenance mode. In maintenance mode normal users are shown a maintenance
    screen, but admin users can still login and use the system as normal.

    This must be added to the middleware variable in settings and must come after
    "django.contrib.auth.middleware.AuthenticationMiddleware" as it needs access to
    the authenticated user.
    """
from django.core.exceptions import MiddlewareNotUsed
from django.shortcuts import render

from cobalt import settings


class MaintenanceModeMiddleware:
    def __init__(self, get_response):
        """This is called when the webserver starts. If we are not in maintenance mode then
        we can disable ourselves"""

        if settings.MAINTENANCE_MODE != "ON":
            raise MiddlewareNotUsed

        print(
            "\n\n*** Maintenance mode is on. Disable by changing environment variable MAINTENANCE_MODE ***"
        )
        print("*** Only superusers can access the system in maintenance mode. ***\n\n")

        # Maintenance mode is on - store get_response
        self.get_response = get_response

    def __call__(self, request):
        """This is called for every request if we are in maintenance mode"""

        response = self.get_response(request)

        # Allow superusers plus access to the login page and ses webhook (or it sends a million error emails)
        if request.user.is_superuser or request.META["PATH_INFO"] in [
            "/accounts/login/",
            "/notifications/ses/event-webhook/",
        ]:
            return response
        else:
            return render(request, "errors/503.html", status=503)
