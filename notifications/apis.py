from cobalt.settings import GLOBAL_ORG
from notifications.views import send_cobalt_bulk_sms


def notifications_api_sms_file_upload_v1(request, file):
    """API call to upload a file and send SMS messages"""

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
    status = "success" if len(sent_users) > 0 else "failure"

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
