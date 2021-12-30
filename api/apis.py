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
from enum import Enum

from fcm_django.models import FCMDevice
from ninja import Router, File, NinjaAPI, Schema
from ninja.files import UploadedFile

from accounts.backend import CobaltBackend
from api.core import api_rbac
from masterpoints.factories import masterpoint_factory_creator
from notifications.apis import notifications_api_sms_file_upload_v1


class APIStatus:
    """Status messages from the API"""

    SUCCESS = "Success"
    FAILURE = "Failure"
    ACCESS_DENIED = "Access Denied"


class ErrorV1(Schema):
    """Standard error format"""

    status: str
    message: str


class UnauthorizedV1(Schema):
    """Standard error format"""

    detail: str


router = Router()
api = NinjaAPI()


@router.get("/keycheck/v1.0")
def key_check_v1(request):
    """Allow a developer to check that their key is valid"""
    return f"Your key is valid. You are authenticated as {request.auth}."


# class SmsResponseV1(Schema):
#     """Success response format from sms_file_upload"""
#
#     status: str
#     sender: str
#     filename: str
#     attempted: int
#     sent: int


@router.post(
    "/sms-file-upload/v1.0",
    # response={200: SmsResponseV1, 401: UnauthorizedV1, 403: ErrorV1},
    summary="SMS file upload API for distribution of different messages to a list of players.",
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

    return notifications_api_sms_file_upload_v1(request, file)


class UserDataResponseV1(Schema):
    """Response format from mobile_client_register_v1"""

    class UserResponse(Schema):
        first_name: str
        last_name: str
        system_number: int

    status: str
    user: UserResponse


class MobileClientRegisterRequestV1(Schema):
    """Request format from mobile_client_register_v1"""

    username: str = ""
    password: str = ""
    fcm_token: str = ""


@router.post(
    "/mobile-client-register/v1.0",
    summary="Register a mobile client to receive notifications.",
    response={
        200: UserDataResponseV1,
        403: ErrorV1,
    },
    # Disable global authorisation, we will check this ourselves
    auth=None,
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

    # Try to Authenticate the user
    user = CobaltBackend().authenticate(request, data.username, data.password)

    if user:
        # Save device
        FCMDevice(user=user, registration_id=data.fcm_token).save()

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


@router.get(
    "/system-number-lookup/v1.0",
    summary="Get name from system number",
    response={
        200: UserDataResponseV1,
        404: ErrorV1,
    },
    # Disable global authorisation, this can be called by anyone
    auth=None,
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
