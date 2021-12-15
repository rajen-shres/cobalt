from cobalt.settings import GLOBAL_ORG
from notifications.views import send_cobalt_bulk_sms


def notifications_api_sms_file_upload_v1(request, file):
    """API call to upload a file and send SMS messages"""

    data = {}
    header_msg = ""

    for line in file.readlines():
        number, msg = line.decode("utf-8").split("\t")
        number = int(number)
        if isinstance(number, int):
            data[number] = msg.replace("<NL>", "\n")
        else:
            header_msg += f"Invalid row, no {GLOBAL_ORG} number found\n -->{line}\n"

    if header_msg == "":
        header_msg = None

    success_count = send_cobalt_bulk_sms(
        msg_dict=data, admin=request.auth, description=file.name, header_msg=header_msg
    )

    status = "Success" if success_count > 0 else "Failure"

    return {
        "status": status,
        "sender": request.auth.__str__(),
        "filename": file.name,
        "attempted": len(data),
        "sent": success_count,
    }
