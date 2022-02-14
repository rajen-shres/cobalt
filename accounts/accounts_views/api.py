from django.contrib import auth
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from fcm_django.models import FCMDevice


def create_user_session_id(user):
    """Create a new session for a user. Used by the mobile API when we register a new device
    so it can login the webpage view using only the session_id and doesn't need to come in through
    the login page.
    """

    # Create new session for user
    session = SessionStore(None)
    session.clear()
    session.cycle_key()
    session[auth.SESSION_KEY] = user._meta.pk.value_to_string(user)
    session[auth.BACKEND_SESSION_KEY] = "accounts.backend.CobaltBackend"
    session[auth.HASH_SESSION_KEY] = user.get_session_auth_hash()
    session.save()

    return session.session_key


def delete_fcm_device_ajax(request):
    """Ajax call to delete an FCM device"""

    device_id = request.GET.get("device_id")
    device = get_object_or_404(FCMDevice, id=device_id)
    if device.user != request.user:
        response_data = {"message": "Error. This is not your device."}
        return JsonResponse({"data": response_data})

    device.delete()
    response_data = {"message": "Success"}
    return JsonResponse({"data": response_data})


def delete_session_ajax(request):
    """Ajax call to delete a session"""

    session_id = request.GET.get("session_id")

    session = get_object_or_404(Session, pk=session_id)

    if (
        "_auth_user_id" in session.get_decoded()
        and int(session.get_decoded()["_auth_user_id"]) == request.user.id
    ):
        session.delete()
        response_data = {"message": "Success"}
    else:
        response_data = {"message": "Error. No matching session found."}
    return JsonResponse({"data": response_data})
