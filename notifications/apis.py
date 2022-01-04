from copy import copy

from fcm_django.models import FCMDevice

import api.apis as api_app
from cobalt.settings import GLOBAL_ORG
from notifications.models import RealtimeNotification
from notifications.views import send_cobalt_bulk_sms


def notifications_api_sms_file_upload_v1(request, file):
    """API call to upload a file and send SMS messages"""

    from api.apis import APIStatus

    data = []
    invalid_lines = []
    lines_in_file = 0

    for line in file.readlines():
        lines_in_file += 1
        line = line.decode("utf-8").strip()
        try:
            number, msg = line.split("\t")
            number = int(number)
            if isinstance(number, int):
                if len(msg.strip()) > 0:
                    data.append((number, msg.replace("<NL>", "\n")))
                else:
                    invalid_lines.append(
                        f"Line {lines_in_file}. No message found. : {line}"
                    )
            else:
                invalid_lines.append(
                    f"Line {lines_in_file}. No {GLOBAL_ORG} number found. : {line}"
                )
        except Exception as exc:
            if "too many values to unpack" in exc.__str__():
                invalid_lines.append(
                    f"Line {lines_in_file}. Too many tab characters in row. : {line}"
                )
            elif "not enough values to unpack" in exc.__str__():
                invalid_lines.append(
                    f"Line {lines_in_file}. No tab character found in row. : {line}"
                )
            elif "invalid literal for int" in exc.__str__():
                invalid_lines.append(
                    f"Line {lines_in_file}. Invalid {GLOBAL_ORG} number. : {line}"
                )
            else:
                invalid_lines.append(f"Line {lines_in_file}. Invalid row {exc}: {line}")

    sent_users, unregistered_users, uncontactable_users = send_cobalt_bulk_sms(
        msg_list=data,
        admin=request.auth,
        description=file.name,
        invalid_lines=invalid_lines,
        total_file_rows=lines_in_file,
    )

    # If we sent anything, we were successful
    status = APIStatus.SUCCESS if len(sent_users) > 0 else APIStatus.FAILURE

    return {
        "status": status,
        "sender": request.auth.__str__(),
        "filename": file.name,
        "counts": {
            "total_lines_in_file": lines_in_file,
            "valid_lines_in_file": len(data),
            "invalid_lines_in_file": lines_in_file - len(data),
            "registered_users_in_file": len(data) - len(unregistered_users),
            "registered_contactable_users_in_file": len(data)
            - len(unregistered_users)
            - len(uncontactable_users),
            "sent": len(sent_users),
        },
        "errors": {
            "invalid_lines": invalid_lines,
            "unregistered_users": unregistered_users,
            "uncontactable_users": uncontactable_users,
            "sent_users": sent_users,
        },
    }


def _notifications_api_common_messages_for_user_v1(fcm_token_object, messages):
    """Common code to handle returning messages"""

    if not messages:
        return 404, {"status": api_app.APIStatus.FAILURE, "message": "No data found"}

    # return messages as list
    return_messages = []

    # mark messages as read now
    for message in messages:
        return_messages.append(message.msg)
        message.has_been_read = True
        message.save()

    return 200, {
        "status": api_app.APIStatus.SUCCESS,
        "un_read_messages": return_messages,
    }


def notifications_api_unread_messages_for_user_v1(fcm_token):
    """Send any unread notifications (FCM) for a user"""

    fcm_token_object = FCMDevice.objects.filter(registration_id=fcm_token).first()
    if not fcm_token_object:
        return 403, {
            "status": api_app.APIStatus.ACCESS_DENIED,
            "message": "Token is invalid",
        }

    messages = RealtimeNotification.objects.filter(has_been_read=False).filter(member=fcm_token_object.user).order_by('-pk')

    return _notifications_api_common_messages_for_user_v1(fcm_token_object, messages)


def notifications_api_latest_messages_for_user_v1(fcm_token):
    """Send latest notifications (FCM) for a user regardless if read or not"""

    fcm_token_object = FCMDevice.objects.filter(registration_id=fcm_token).first()
    if not fcm_token_object:
        return 403, {
            "status": api_app.APIStatus.ACCESS_DENIED,
            "message": "Token is invalid",
        }

    messages = RealtimeNotification.objects.filter(member=fcm_token_object.user).order_by('-pk')[:50]

    return _notifications_api_common_messages_for_user_v1(fcm_token_object, messages)