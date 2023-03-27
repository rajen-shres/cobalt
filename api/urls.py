"""This is the main entry point for the cobalt API. The API is a separate Django app as
this makes things cleaner and easier to manage than having the (relatively small) API code
spread across lots of modules."""
import logging

from django.urls import path
import urllib.parse
from ninja import NinjaAPI
from ninja.errors import ValidationError

from accounts.models import User, APIToken
from .apis import router as cobalt_router
from ninja.security import (
    APIKeyQuery,
    APIKeyHeader,
    APIKeyCookie,
    HttpBearer,
    HttpBasicAuth,
)

from .models import ApiLog

logger = logging.getLogger("cobalt")


def log_api_call(request, user=None):
    """Log a call to the API. For anonymous calls the user will be empty"""

    # All API calls are versioned. Log call details. Throw error if version not set
    url_parts = urllib.parse.urlparse(request.path)
    path_parts = url_parts[2].rpartition("/")
    ApiLog(api=path_parts[0], version=path_parts[2], admin=user).save()


class AuthCheck:
    """This is the core authentication method. Other classes inherit from this and provide
    different ways to obtain the same key from the client."""

    def authenticate(self, request, key):
        """Returns the user associated with this key or None (invalid)"""
        api_key = APIToken.objects.filter(token=key).first()
        if api_key:
            log_api_call(request, api_key.user)
            return api_key.user


class QueryKey(AuthCheck, APIKeyQuery):
    """Get the key from the query"""

    pass


class HeaderKey(AuthCheck, APIKeyHeader):
    """Get the key from the header"""

    pass


# # Needs CSRF token. Look at later
# class CookieKey(AuthCheck, APIKeyCookie):
#     """Get the key from the cookie"""
#     pass


class BearerKey(AuthCheck, HttpBearer):
    """Get the key from the HttpBearer"""

    pass


app_name = "api"

api = NinjaAPI(
    urls_namespace=f"{app_name}:api",
    docs_url="/docs/",
    auth=[QueryKey(), HeaderKey(), BearerKey()],
)


# Temporary handler to look at helping Peter Busch with getting this to work from VB .NET


@api.exception_handler(ValidationError)
def custom_validation_errors(request, exc):
    logger.warning("Validation error from API")
    logger.warning(f"method: {request.method}")
    logger.warning(f"headers: {request.headers}")
    logger.warning(f"content_type: {request.content_type}")
    logger.warning(f"content_params: {request.content_params}")
    logger.warning(f"auth: {request.auth}")
    logger.warning(f"accepted_types: {request.accepted_types}")
    logger.warning(f"GET: {request.GET}")
    logger.warning(f"POST: {request.POST}")
    logger.warning(exc.errors)
    return api.create_response(request, {"detail": exc.errors}, status=422)


# You can have multiple routers so if this gets too big it can be split up.
# We use an unnecessary namespace to make this easy to do later if required.
api.add_router("cobalt", cobalt_router)

urlpatterns = [
    path("", api.urls),
]
