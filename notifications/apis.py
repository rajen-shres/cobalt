from cobalt.settings import GLOBAL_ORG
from notifications.views import send_cobalt_bulk_sms


def notifications_api_sms_file_upload_v1(request, file):
    """API call to upload a file and send SMS messages"""

    data = {}
    header_msg = ""

    for line in file.readlines():
        try:
            number, msg = line.decode("utf-8").split("\t")
            number = int(number)
            if isinstance(number, int):
                if len(msg.strip()) > 0:
                    data[number] = msg.replace("<NL>", "\n")
                else:
                    header_msg += f"No message found.\n -->{line}\n"
            else:
                header_msg += f"Invalid row, no {GLOBAL_ORG} number found\n -->{line}\n"
        except Exception as exc:
            print(f"Exception found {exc}")
            header_msg += f"Invalid row {exc}: {line}\n"

    # Return empty string for no errors but use None for the database record
    header_msg_send = None if header_msg == "" else header_msg

    success_count = send_cobalt_bulk_sms(
        msg_dict=data,
        admin=request.auth,
        description=file.name,
        header_msg=header_msg_send,
    )

    status = "Success" if success_count > 0 else "Failure"

    return {
        "status": status,
        "sender": request.auth.__str__(),
        "filename": file.name,
        "attempted": len(data),
        "sent": success_count,
        "message": header_msg,
    }
