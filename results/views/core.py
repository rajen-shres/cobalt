from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
import json
import xmltodict


@login_required
def home(request):
    return render(request, "results/home.html")


def parse_usebio_file(filename):
    """read a USEBIO format XML file and turn into a dictionary"""

    with open(filename, "rb") as file:
        xml = file.read()

    json.dumps(xmltodict.parse(xml))

    return xml
