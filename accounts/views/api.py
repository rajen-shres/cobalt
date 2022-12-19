from django.contrib import auth
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from fcm_django.models import FCMDevice

from accounts.models import User, UnregisteredUser
from cobalt.settings import ALL_SYSTEM_ACCOUNTS
from masterpoints.views import search_mpc_users_by_name


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


def search_for_user_in_cobalt_and_mpc(first_name_search, last_name_search):
    """Search for a user in Cobalt or MPC"""

    # Cobalt registered users
    registered_users = User.objects.exclude(pk__in=ALL_SYSTEM_ACCOUNTS)
    if first_name_search:
        registered_users = registered_users.filter(
            first_name__istartswith=first_name_search
        )
    if last_name_search:
        registered_users = registered_users.filter(
            last_name__istartswith=last_name_search
        )

    registered_users = registered_users[:11]

    # Cobalt unregistered users
    un_registered_users = UnregisteredUser.objects.all()
    if first_name_search:
        un_registered_users = un_registered_users.filter(
            first_name__istartswith=first_name_search
        )
    if last_name_search:
        un_registered_users = un_registered_users.filter(
            last_name__istartswith=last_name_search
        )

    un_registered_users = un_registered_users[:11]

    # Masterpoints Centre
    mpc_users = search_mpc_users_by_name(first_name_search, last_name_search)

    # Combine the lists
    user_list = []
    already_present = []
    for registered_user in registered_users[:10]:
        if registered_user.system_number not in already_present:
            user_list.append(
                {
                    "system_number": registered_user.system_number,
                    "first_name": registered_user.first_name,
                    "last_name": registered_user.last_name,
                    "home_club": None,
                    "source": "registered",
                }
            )
            already_present.append(registered_user.system_number)

    for un_registered_user in un_registered_users[:10]:
        if un_registered_user.system_number not in already_present:
            user_list.append(
                {
                    "system_number": un_registered_user.system_number,
                    "first_name": un_registered_user.first_name,
                    "last_name": un_registered_user.last_name,
                    "mpc_email": None,
                    "home_club": None,
                    "source": "unregistered",
                }
            )
            already_present.append(un_registered_user.system_number)

    # A user might not be in the top 11 of registered or unregistered users, but could still be in the top
    # 11 of MPC users, in which case they will be reported incorrectly
    # There can be no overlap between registered and unregistered, so just double check the MPC ones
    check_user_list = [mpc_user["ABFNumber"] for mpc_user in mpc_users[:10]]

    # Check real users
    really_registered = User.objects.filter(system_number__in=check_user_list)
    for registered_user in really_registered:
        if registered_user.system_number not in already_present:
            user_list.append(
                {
                    "system_number": registered_user.system_number,
                    "first_name": registered_user.first_name,
                    "last_name": registered_user.last_name,
                    "home_club": None,
                    "source": "registered",
                }
            )
            already_present.append(registered_user.system_number)

    # Check real un_registered
    really_un_registered = UnregisteredUser.objects.filter(
        system_number__in=check_user_list
    )
    for un_registered_user in really_un_registered[:10]:
        if un_registered_user.system_number not in already_present:
            user_list.append(
                {
                    "system_number": un_registered_user.system_number,
                    "first_name": un_registered_user.first_name,
                    "last_name": un_registered_user.last_name,
                    # "mpc_email": un_registered_user.email,
                    "home_club": None,
                    "source": "unregistered",
                }
            )
            already_present.append(un_registered_user.system_number)

    for mpc_user in mpc_users[:10]:
        if int(mpc_user["ABFNumber"]) not in already_present:
            user_list.append(
                {
                    "system_number": mpc_user["ABFNumber"],
                    "first_name": mpc_user["GivenNames"],
                    "last_name": mpc_user["Surname"],
                    "home_club": mpc_user["ClubName"],
                    "mpc_email": mpc_user["EmailAddress"],
                    "source": "mpc",
                }
            )

    # Sort
    user_list = sorted(user_list, key=lambda d: d["first_name"])

    # Check if we have more data anywhere. We ask for 11 but only use 10
    if (
        len(registered_users) > 10
        or len(un_registered_users) > 10
        or len(mpc_users) > 10
    ):
        more_data = True
    else:
        more_data = False

    return user_list, more_data
