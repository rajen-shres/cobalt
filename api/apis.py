"""These are the supported APIs for Cobalt.

Authentication is handled in the urls.py module, so by the time you get here you are dealing
with an authenticated user. Functions in here are still responsible for rbac calls to
handle access.

"""
import time

from ninja import Router, File
from ninja.files import UploadedFile

from cobalt.settings import GLOBAL_ORG
from notifications.views import send_cobalt_bulk_sms

router = Router()


@router.get("/add")
def add(request, a: int, b: int):
    return {"result": a + b}


@router.get("/keycheck/v1.0")
def key_check(request):
    """Allow a developer to check that their key is valid"""
    return f"Your key is valid. You are authenticated as {request.auth}."


@router.post("/sms-file-upload/v1.0")
def upload_a_file(request, file: UploadedFile = File(...)):
    """Allow scorers to upload a file with ABF numbers and messages to send to members.

    File format is <abf_number>\t<message>

    The filename is used as the description.

    If the message contains <NL> then change this to a \n.
    """
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

    return {
        "status": "Success",
        "sender": request.auth.__str__(),
        "filename": file.name,
        "attempted": len(data),
        "sent": success_count,
    }
