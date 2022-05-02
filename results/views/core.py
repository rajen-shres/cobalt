from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
import json
import xmltodict
from django.utils.datetime_safe import datetime

from cobalt.settings import MEDIA_ROOT
from results.models import ResultsFile, PlayerSummaryResult
from django.contrib.humanize.templatetags.humanize import ordinal


@login_required
def home(request):
    return render(request, "results/home.html")


def parse_usebio_file(results_file):
    """read a USEBIO format XML file that has already been uploaded and turn into a dictionary"""

    file_name = f"{MEDIA_ROOT}/{results_file.results_file.name}"

    with open(file_name, "rb") as file:
        xml = file.read()

    xml = xmltodict.parse(xml)

    return xml["USEBIO"]["EVENT"]


def create_player_records_from_usebio_format(results_file: ResultsFile, xml: dict):
    """take in a xml usebio structure and generate the PlayerSummaryResult records"""

    #    results_file = get_object_or_404(ResultsFile, pk=results_file_id)

    event_name = xml["TITLE"]
    event_date_str = xml["DATE"]
    event_date = datetime.strptime(event_date_str, "%d/%m/%Y")

    for detail in xml["PARTICIPANTS"]["PAIR"]:
        percentage = detail["PERCENTAGE"]
        position = detail["PLACE"]
        place = ordinal(position)
        for player in detail["PLAYER"]:
            player_system_number = player["NATIONAL_ID_NUMBER"]

            if player_system_number:
                PlayerSummaryResult(
                    player_system_number=player_system_number,
                    results_file=results_file,
                    result_date=event_date,
                    position=position,
                    percentage=percentage,
                    result_string=f"{place} in {event_name} at {results_file.organisation}",
                    event_name=event_name,
                ).save()
