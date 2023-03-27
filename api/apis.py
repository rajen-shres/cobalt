"""These are the supported APIs for Cobalt.

Authentication is handled in the urls.py module, so by the time you get here you are dealing
with an authenticated user. Functions in here are still responsible for rbac calls to
handle access.

Code here should be as short as possible, if anything more complex is required you should
call a function in the 'home' module for the thing you are doing.

APIs should all be versioned with /vx.y at the end of the URI. This is automatically logged
every time an API is called.

APIs should all return JSON with at least one parameter e.g.

    {'status': 'Success'}

    or

    {'status: 'Failure'}

    or

    {'status: 'Access Denied'}

"""
from typing import List

from django.http import HttpResponse
from fcm_django.models import FCMDevice
from firebase_admin.messaging import Message, Notification
from ninja import Router, File, NinjaAPI, Schema, Form
from ninja.errors import ValidationError, HttpError
from ninja.files import UploadedFile

from accounts.backend import CobaltBackend
from accounts.views.api import create_user_session_id
from api.core import api_rbac
import api.urls as api_urls
from cobalt.settings import GLOBAL_TITLE
from logs.views import log_event
from masterpoints.factories import masterpoint_factory_creator
from notifications.apis import (
    notifications_api_file_upload_v1,
    notifications_api_unread_messages_for_user_v1,
    notifications_api_latest_messages_for_user_v1,
    notifications_delete_message_for_user_v1,
    notifications_delete_all_messages_for_user_v1,
)
from notifications.models import RealtimeNotification

router = Router()
api = NinjaAPI()

#########################################################
# Data Structures                                       #
#########################################################


class APIStatus:
    """Status messages from the API"""

    SUCCESS = "Success"
    FAILURE = "Failure"
    ACCESS_DENIED = "Access Denied"


class StatusResponseV1(Schema):
    """Standard error/response format when no data is returned"""

    status: str
    message: str


class UnauthorizedV1(Schema):
    """Standard error format"""

    detail: str


# class SmsResponseV1(Schema):
#     """Success response format from sms_file_upload"""
#
#     status: str
#     sender: str
#     filename: str
#     attempted: int
#     sent: int


class UserDataResponseV1(Schema):
    """Response format from mobile_client_register_v1"""

    class UserResponseV1(Schema):
        first_name: str
        last_name: str
        system_number: int

    status: str
    user: UserResponseV1


class UserDataResponseV11(Schema):
    """Response format from mobile_client_register_v1.1"""

    class UserResponseV1(Schema):
        first_name: str
        last_name: str
        system_number: int
        session_id: str

    status: str
    user: UserResponseV1


class MobileClientRegisterRequestV1(Schema):
    """Request format from mobile_client_register_v1"""

    username: str = ""
    password: str = ""
    fcm_token: str = ""


class MobileClientRegisterRequestV11(Schema):
    """Request format from mobile_client_register_v1.1"""

    username: str = ""
    password: str = ""
    fcm_token: str = ""
    OS: str = ""
    name: str = ""


class MobileClientUpdateRequestV1(Schema):
    """Request format from mobile_client_update_v1"""

    old_fcm_token: str = ""
    new_fcm_token: str = ""


class MobileClientFCMRequestV1(Schema):
    fcm_token: str


class UnreadMessageV1(Schema):
    id: int
    message: str
    created_datetime: str


class MobileClientUnreadMessagesResponseV1(Schema):
    status: str
    un_read_messages: List[UnreadMessageV1]


class MobileClientSingleMessageRequestV1(Schema):
    """Structure for requests that access a single message by id"""

    fcm_token: str
    message_id: int


class NotificationFileUploadV1(Schema):
    sender_identification: str = None


@router.get("/keycheck/v1.0", tags=["Utility"])
def key_check_v1(request):
    """Allow a developer to check that their key is valid"""
    return f"Your key is valid. You are authenticated as {request.auth}."


@router.post(
    "/sms-file-upload/v1.0",
    # response={200: SmsResponseV1, 401: UnauthorizedV1, 403: ErrorV1},
    summary="Deprecated. SMS file upload API for distribution of different messages to a list of players.",
    tags=["Notifications"],
)
def sms_file_upload_v1(request, file: UploadedFile = File(...)):
    """Allow scorers to upload a file with ABF numbers and messages to send to members.

    File format is abf_number[tab character (\\t)]message

    The filename is used as the description.

    If the message contains \\<NL\\> then we change this to a newline (\\n).

    Messages over 140 characters will be sent as multiple SMSs.
    """

    # Check access
    role = "notifications.realtime_send.edit"
    status, return_error = api_rbac(request, role)
    if not status:
        return return_error

    return notifications_api_file_upload_v1(request, file)


@router.post(
    "/notification-file-upload/v1.0",
    # response={200: SmsResponseV1, 401: UnauthorizedV1, 403: ErrorV1},
    summary="Notification file upload API for distribution of different messages to a list of players.",
    tags=["Notifications"],
)
def notification_file_upload_v1(
    request, data: NotificationFileUploadV1 = Form(...), file: UploadedFile = File(...)
):
    """Allow scorers to upload a file with ABF numbers and messages to send to members.

    File format is abf_number[tab character (\\t)]message

    The filename is used as the description.

    If the message contains \\<NL\\> then we change this to a newline (\\n).

    Messages are sent through Google Firebase Messaging to a mobile app.
    """

    # Check access
    role = "notifications.realtime_send.edit"
    status, return_error = api_rbac(request, role)
    if not status:
        return return_error

    return notifications_api_file_upload_v1(request, file, data.sender_identification)


@router.post(
    "/mobile-client-register/v1.0",
    summary="Register a mobile client to receive notifications.",
    response={
        200: UserDataResponseV1,
        403: StatusResponseV1,
    },
    # Disable global authorisation, we will check this ourselves
    auth=None,
    tags=["Mobile App"],
)
def mobile_client_register_v1(request, data: MobileClientRegisterRequestV1):
    """
    Called by the Flutter front end to register a new FCM Token for a user.
    User is NOT authenticated, but username and password are passed in.

    Args:

          username - username of this user, can be ABF No, email or actual username, same as login

          password - as provided by user

          fcm_token - client device's Google Firebase Cloud Messaging token. Used to send messages to this user/device

    """

    # Log Api call ourselves as we aren't going through authentication
    api_urls.log_api_call(request)

    # Generic Log
    log_event(
        "Unknown",
        "INFO",
        "Mobile",
        "Registration",
        f"Mobile Register Client 1 - Attempt using username:{data.username} fcm_token: {data.fcm_token}",
    )

    # Validate
    if data.fcm_token == "":
        # Don't provide any details about failures for security reasons
        return 403, {"status": APIStatus.FAILURE, "message": APIStatus.ACCESS_DENIED}

    # Try to Authenticate the user
    user = CobaltBackend().authenticate(request, data.username, data.password)

    if user:
        # Save device
        fcm_device = FCMDevice(user=user, registration_id=data.fcm_token)
        fcm_device.save()

        # Mark all messages previously sent to the user as read to prevent swamping them with old messages
        RealtimeNotification.objects.filter(member=user).update(has_been_read=True)

        # Create a welcome message
        welcome_msg = (
            f"Hi {user.first_name},\n"
            f"This device is now set up to receive messages from {GLOBAL_TITLE}.\n\n"
            f"You can manage your devices through Settings within {GLOBAL_TITLE}."
        )
        RealtimeNotification(
            member=user,
            admin=user,
            msg=welcome_msg,
        ).save()
        msg = Message(
            notification=Notification(
                title=f"Welcome to {GLOBAL_TITLE} messaging.",
                body="Welcome!\n\nNew device successfully registered.",
            )
        )
        fcm_device.send_message(msg)

        return 200, {
            "status": APIStatus.SUCCESS,
            "user": {
                "first_name": user.first_name,
                "last_name": user.last_name,
                "system_number": user.system_number,
            },
        }

    # Don't provide any details about failures for security reasons
    return 403, {"status": APIStatus.FAILURE, "message": APIStatus.ACCESS_DENIED}


@router.post(
    "/mobile-client-register/v1.1",
    summary="Register a mobile client to receive notifications.",
    response={
        200: UserDataResponseV11,
        403: StatusResponseV1,
    },
    # Disable global authorisation, we will check this ourselves
    auth=None,
    tags=["Mobile App"],
)
def mobile_client_register_v11(request, data: MobileClientRegisterRequestV11):
    """
    Called by the Flutter front end to register a new FCM Token for a user.
    User is NOT authenticated, but username and password are passed in.

    Args:

          username - username of this user, can be ABF No, email or actual username, same as login

          password - as provided by user

          fcm_token - client device's Google Firebase Cloud Messaging token. Used to send messages to this user/device

          OS - operating system of mobile device

          name - name of mobile device

    """

    # Log Api call ourselves as we aren't going through authentication
    api_urls.log_api_call(request)

    # Generic Log
    log_event(
        "Unknown",
        "INFO",
        "Mobile",
        "Registration",
        f"Mobile Client Register V11 - Attempt using username:{data.username} fcm_token: {data.fcm_token} os:{data.OS} name: {data.name}",
    )

    # Validate
    if not data.fcm_token:
        log_event(
            "Unknown",
            "ERROR",
            "Mobile",
            "Registration",
            f"Mobile Client Register V11 - FCM Token is None. Attempt using username:{data.username} fcm_token: {data.fcm_token}",
        )
        # Don't provide any details about failures for security reasons
        return 403, {"status": APIStatus.FAILURE, "message": APIStatus.ACCESS_DENIED}

    if data.fcm_token == "":
        log_event(
            "Unknown",
            "ERROR",
            "Mobile",
            "Registration",
            f"Mobile Client Register V11 - FCM Token is empty string. Attempt using username:{data.username} fcm_token: {data.fcm_token}",
        )
        # Don't provide any details about failures for security reasons
        return 403, {"status": APIStatus.FAILURE, "message": APIStatus.ACCESS_DENIED}

    # Try to Authenticate the user
    user = CobaltBackend().authenticate(request, data.username, data.password)

    if not user:
        log_event(
            "Unknown",
            "ERROR",
            "Mobile",
            "Registration",
            f"Mobile Client Register V11 - User not found. Attempt using username:{data.username} fcm_token: {data.fcm_token}",
        )
        # Don't provide any details about failures for security reasons
        return 403, {"status": APIStatus.FAILURE, "message": APIStatus.ACCESS_DENIED}

    # Set a value for an empty name
    if data.name == "":
        data.name = "Mobile Device"

    # Delete token if used before (token will be the same if a user logs out and another logs in, same device)
    FCMDevice.objects.filter(registration_id=data.fcm_token).delete()

    # Save new device
    fcm_device = FCMDevice(
        user=user, type=data.OS, name=data.name, registration_id=data.fcm_token
    )
    fcm_device.save()

    log_event(
        "Unknown",
        "INFO",
        "Mobile",
        "Registration",
        f"Mobile Client Register V11 - Registered new fcm_device. Attempt using username:{data.username} fcm_token: {data.fcm_token}",
    )

    # Mark all messages previously sent to the user as read to prevent swamping them with old messages
    RealtimeNotification.objects.filter(member=user).update(has_been_read=True)

    # Create a welcome message
    welcome_msg = (
        f"Hi {user.first_name},\n"
        f"This device ({data.name}) is now set up to receive messages from {GLOBAL_TITLE}.\n\n"
        f"You can manage your devices through Settings within {GLOBAL_TITLE}."
    )
    RealtimeNotification(
        member=user,
        admin=user,
        msg=welcome_msg,
    ).save()
    msg = Message(
        notification=Notification(
            title=f"Welcome to {GLOBAL_TITLE} messaging.",
            body="Welcome!\n\nNew device successfully registered.",
        )
    )
    fcm_device.send_message(msg)

    # Get a session id for this user
    session_id = create_user_session_id(user)

    return 200, {
        "status": APIStatus.SUCCESS,
        "user": {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "system_number": user.system_number,
            "session_id": session_id,
        },
    }


@router.get(
    "/system-number-lookup/v1.0",
    summary="Get name from system number",
    response={
        200: UserDataResponseV1,
        404: StatusResponseV1,
    },
    # Disable global authorisation, this can be called by anyone
    auth=None,
    tags=["Utility"],
)
def system_number_lookup_v1(request, system_number: int):
    # Masterpoints uses a factory - get an instance to talk to
    mp_source = masterpoint_factory_creator()

    # Call function to lookup system_number
    status, return_value = mp_source.system_number_lookup_api(system_number)

    if status:
        return 200, {
            "status": APIStatus.SUCCESS,
            "user": {
                "first_name": return_value[0],
                "last_name": return_value[1],
                "system_number": system_number,
            },
        }

    else:
        return 404, {"status": APIStatus.FAILURE, "message": return_value}


@router.post(
    "/mobile-client-update/v1.0",
    summary="Update a users FCM Token, takes old token as security check",
    response={
        200: UserDataResponseV1,
        404: StatusResponseV1,
    },
    # Disable global authorisation, we use the old token as the authentication method
    auth=None,
    tags=["Mobile App"],
)
def mobile_client_update_v1(request, data: MobileClientUpdateRequestV1):
    """Called to update the FCM token"""

    # Log Api call ourselves as we aren't going through authentication
    api_urls.log_api_call(request)

    # Not sure if we really need this. Log it to find out.

    log_event(
        "Unknown",
        "INFO",
        "Mobile",
        "Update",
        f"Mobile Client Update V1 - Attempt using old token: {data.old_fcm_token} new_token: {data.new_fcm_token}",
    )

    # Validate
    if not data.new_fcm_token:
        log_event(
            "Unknown",
            "ERROR",
            "Mobile",
            "Update",
            f"Mobile Client Update V1 - New FCM Token is None. Old token : {data.old_fcm_token}",
        )
        # Don't provide any details about failures for security reasons
        return 404, {"status": APIStatus.FAILURE, "message": APIStatus.ACCESS_DENIED}

    if data.new_fcm_token == "":
        log_event(
            "Unknown",
            "ERROR",
            "Mobile",
            "Update",
            f"Mobile Client Update V1 - New FCM Token is Empty string. Old token : {data.old_fcm_token}",
        )
        # Don't provide any details about failures for security reasons
        return 404, {"status": APIStatus.FAILURE, "message": APIStatus.ACCESS_DENIED}

    fcm_device = (
        FCMDevice.objects.filter(registration_id=data.old_fcm_token)
        .select_related("user")
        .first()
    )

    if not fcm_device:
        return 404, {
            "status": APIStatus.FAILURE,
            "message": f"Existing token not found ({data.old_fcm_token})",
        }

    fcm_device.registration_id = data.new_fcm_token
    fcm_device.save()

    return 200, {
        "status": APIStatus.SUCCESS,
        "user": {
            "first_name": fcm_device.user.first_name,
            "last_name": fcm_device.user.last_name,
            "system_number": fcm_device.user.system_number,
        },
    }


@router.post(
    "/mobile-client-get-unread-messages/v1.0",
    summary="Get unread messages for a user by passing FCM_token",
    response={
        200: MobileClientUnreadMessagesResponseV1,
        403: StatusResponseV1,
        404: StatusResponseV1,
    },
    # Disable global authorisation, we use the token as the authentication method
    auth=None,
    tags=["Mobile App"],
)
def api_notifications_unread_messages_for_user_v1(
    request, data: MobileClientFCMRequestV1
):
    """Return any unread messages for this user"""

    # Log Api call ourselves as we aren't going through authentication
    api_urls.log_api_call(request)

    return notifications_api_unread_messages_for_user_v1(data.fcm_token)


@router.post(
    "/mobile-client-get-latest-messages/v1.0",
    summary="Get latest messages (max 50) for a user, regardless of if they are read, by passing FCM_token",
    response={
        200: MobileClientUnreadMessagesResponseV1,
        403: StatusResponseV1,
        404: StatusResponseV1,
    },
    # Disable global authorisation, we use the token as the authentication method
    auth=None,
    tags=["Mobile App"],
)
def api_notifications_latest_messages_for_user_v1(
    request, data: MobileClientFCMRequestV1
):
    """Return last 50 messages for this user"""

    # Log Api call ourselves as we aren't going through authentication
    api_urls.log_api_call(request)

    return notifications_api_latest_messages_for_user_v1(data.fcm_token)


@router.post(
    "/mobile-client-delete-message/v1.0",
    summary="Delete a single message",
    response={
        200: StatusResponseV1,
        403: StatusResponseV1,
        404: StatusResponseV1,
    },
    # Disable global authorisation, we use the token as the authentication method
    auth=None,
    tags=["Mobile App"],
)
def api_notifications_delete_message_for_user_v1(
    request, data: MobileClientSingleMessageRequestV1
):
    """Delete a single message"""

    # Log Api call ourselves as we aren't going through authentication
    api_urls.log_api_call(request)

    return notifications_delete_message_for_user_v1(data)


@router.post(
    "/mobile-client-delete-all-messages/v1.0",
    summary="Delete all messages for a user",
    response={
        200: StatusResponseV1,
        403: StatusResponseV1,
        404: StatusResponseV1,
    },
    # Disable global authorisation, we use the token as the authentication method
    auth=None,
    tags=["Mobile App"],
)
def api_notifications_delete_all_messages_for_user_v1(
    request, data: MobileClientFCMRequestV1
):
    """Delete all message"""

    # Log Api call ourselves as we aren't going through authentication
    api_urls.log_api_call(request)

    return notifications_delete_all_messages_for_user_v1(data)
