"""These are the supported APIs for Cobalt.

Authentication is handled in the urls.py module, so by the time you get here you are dealing
with an authenticated user. Functions in here are still responsible for rbac calls to
handle access.

"""

from ninja import Router, File
from ninja.files import UploadedFile

router = Router()


@router.get("/add")
def add(request, a: int, b: int):
    return {"result": a + b}


@router.get("/keycheck")
def key_check(request):
    return f"Token = {request.auth}"


@router.post("/upload")
def upload_a_file(request, file: UploadedFile = File(...)):
    data = {}
    for line in file.readlines():
        print(line)

    return {"user": request.auth.__str__(), "name": file.name, "len": len(data)}
