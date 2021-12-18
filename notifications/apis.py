from cobalt.settings import GLOBAL_ORG
from notifications.views import send_cobalt_bulk_sms


def notifications_api_sms_file_upload_v1(request, file):
    """API call to upload a file and send SMS messages"""

    data = []
    invalid_lines = []

    for line in file.readlines():
        try:
            number, msg = line.decode("utf-8").split("\t")
            number = int(number)
            if isinstance(number, int):
                if len(msg.strip()) > 0:
                    data.append((number, msg.replace("<NL>", "\n")))
                else:
                    invalid_lines.append("No message found. -->{line}")
            else:
                invalid_lines.append(
                    f"Invalid row, no {GLOBAL_ORG} number found -->{line}"
                )
        except Exception as exc:
            print(f"Exception found {exc}")
            invalid_lines.append(f"Invalid row {exc}: {line}")

    success_count, unregistered_users, uncontactable_users = send_cobalt_bulk_sms(
        msg_list=data,
        admin=request.auth,
        description=file.name,
        invalid_lines=invalid_lines,
    )

    # If we sent anything, we were successful
    status = "success" if success_count > 0 else "failure"

    return {
        "status": status,
        "sender": request.auth.__str__(),
        "filename": file.name,
        "counts": {
            "total_lines_in_file": len(file.read()),
            "valid_lines_in_file": len(data),
            "invalid_lines_in_file": len(file.read()) - len(data),
            "registered_users_in_file": 99,
            "registered_contactable_users_in_file": 99,
            "sent": success_count,
        },
        "errors": {
            "invalid_lines": invalid_lines,
            "unregistered_users": unregistered_users,
            "uncontactable_users": uncontactable_users,
        },
    }
