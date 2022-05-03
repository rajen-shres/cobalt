import pytz
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
import json
import xmltodict
from django.utils import timezone
from django.utils.datetime_safe import datetime
from django.utils.timezone import make_aware

from cobalt.settings import MEDIA_ROOT, TIME_ZONE
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

    # tz = pytz.timezone(TIME_ZONE)
    event_name = xml["EVENT_DESCRIPTION"]
    event_date_str = xml["DATE"]
    event_date = datetime.strptime(event_date_str, "%d/%m/%Y").date()

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


def get_recent_results(user):
    """Return the 5 most recent results for a user. Called by Dashboard"""

    return PlayerSummaryResult.objects.filter(
        player_system_number=user.system_number
    ).order_by("result_date")[:5]


@login_required()
def usebio_mp_pairs_results_summary_view(request, results_file_id):
    """Show the summary results for a usebio format event"""

    # TODO: Error checking, handle ties, one field or two
    # TODO: Link to user and highlight name
    # TODO: Masterpoints show type in title and change colours
    # TODO: Highlight team mates

    results_file = get_object_or_404(ResultsFile, pk=results_file_id)
    usebio = parse_usebio_file(results_file)

    masterpoint_type = usebio["MASTER_POINT_TYPE"].title()

    if usebio["WINNER_TYPE"] == "2":
        # Two fields NS/EW

        ns_scores = []
        ew_scores = []

        for item in usebio["PARTICIPANTS"]["PAIR"]:
            player_1 = item["PLAYER"][0]["PLAYER_NAME"].title()
            player_2 = item["PLAYER"][1]["PLAYER_NAME"].title()
            try:
                player_1_system_number = int(item["PLAYER"][0]["NATIONAL_ID_NUMBER"])
                player_2_system_number = int(item["PLAYER"][1]["NATIONAL_ID_NUMBER"])
            except TypeError:
                player_1_system_number = None
                player_2_system_number = None

            # This may break for ties
            position = int(item["PLACE"])
            masterpoints = int(item["MASTER_POINTS_AWARDED"]) / 100.0
            pair_number = item["PAIR_NUMBER"]
            direction = item["DIRECTION"]
            percentage = item["PERCENTAGE"]

            players_names = f"{player_1} & {player_2}"

            # for couple show name as Mary & David Smith
            surname1 = player_1.split(" ")[-1]
            surname2 = player_2.split(" ")[-1]
            if surname1 == surname2:
                first_name1 = player_1.split(" ")[0]
                players_names = f"{first_name1} & {player_2}"

            # See if this user is in the data and highlight
            if request.user.system_number in [
                player_1_system_number,
                player_2_system_number,
            ]:
                tr_highlight = "bg-warning"
            else:
                tr_highlight = ""

            row = {
                "player_1": player_1,
                "player_2": player_2,
                "players_names": players_names,
                "player_1_system_number": player_1_system_number,
                "player_2_system_number": player_2_system_number,
                "position": position,
                "masterpoints": masterpoints,
                "pair_number": pair_number,
                "percentage": percentage,
                "tr_highlight": tr_highlight,
            }

            if direction == "NS":
                ns_scores.append(row)
            else:
                ew_scores.append(row)

        # sort
        ns_scores = sorted(ns_scores, key=lambda d: d["position"])
        ew_scores = sorted(ew_scores, key=lambda d: d["position"])

        return render(
            request,
            "results/usebio_results_summary_two_field_view.html",
            {
                "usebio": usebio,
                "ns_scores": ns_scores,
                "ew_scores": ew_scores,
                "masterpoint_type": masterpoint_type,
            },
        )
