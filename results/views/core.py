from ddstable import ddstable
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
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

    return xml["USEBIO"]


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


def double_dummy_from_usebio(board):
    """perform a double dummy analysis of a hand.
    This requires libdds.so to be available on the path. See the documentation
    if you need to rebuild this for your OS. It works fine on Linux out of the box. Nothing extra required,
    just pip install ddstable.

    We expect to get part of the USEBIO XML - ['USEBIO']["HANDSET"]["BOARD"][?]

    Data contains a list with direction and suits ('DIRECTION', 'East'), ('CLUBS', 'Q6542'), ('DIAMONDS', '85'),...

    """

    # Build PBN format string

    hand = {}

    print(board)

    for compass in board:
        hand[compass["DIRECTION"]] = {}
        hand[compass["DIRECTION"]]["clubs"] = compass["CLUBS"]
        hand[compass["DIRECTION"]]["diamonds"] = compass["DIAMONDS"]
        hand[compass["DIRECTION"]]["hearts"] = compass["HEARTS"]
        hand[compass["DIRECTION"]]["spades"] = compass["SPADES"]

    print(hand)

    pbn_str = f"E:{hand['North']['spades']}.{hand['North']['hearts']}.{hand['North']['diamonds']}.{hand['North']['clubs']}"
    pbn_str += f" {hand['East']['spades']}.{hand['East']['hearts']}.{hand['East']['diamonds']}.{hand['East']['clubs']}"
    pbn_str += f" {hand['South']['spades']}.{hand['South']['hearts']}.{hand['South']['diamonds']}.{hand['South']['clubs']}"
    pbn_str += f" {hand['West']['spades']}.{hand['West']['hearts']}.{hand['West']['diamonds']}.{hand['West']['clubs']}"

    pbn_bytes = bytes(pbn_str, encoding="utf-8")

    # PBN = b"E:QJT5432.T.6.QJ82 .J97543.K7532.94 87.A62.QJT4.AT75 AK96.KQ8.A98.K63"
    all = ddstable.get_ddstable(pbn_bytes)
    print(all)

    return all
