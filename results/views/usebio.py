import xmltodict
from django.contrib.humanize.templatetags.humanize import ordinal
from django.utils.datetime_safe import datetime

from cobalt.settings import MEDIA_ROOT
from results.models import ResultsFile, PlayerSummaryResult


def parse_usebio_file(results_file):
    """read a USEBIO format XML file that has already been uploaded and turn into a dictionary"""

    file_name = f"{MEDIA_ROOT}/{results_file.results_file.name}"

    with open(file_name, "rb") as file:
        xml = file.read()

    xml = xmltodict.parse(xml)

    return xml["USEBIO"]


def create_player_records_from_usebio_format_pairs(
    results_file: ResultsFile, xml: dict
):
    """take in a xml usebio structure and generate the PlayerSummaryResult records for pairs event"""

    xml = xml.get("EVENT")

    event_name = xml.get("EVENT_DESCRIPTION")
    event_date_str = xml.get("DATE")
    event_date = datetime.strptime(event_date_str, "%d/%m/%Y").date()

    for detail in xml["PARTICIPANTS"]["PAIR"]:
        percentage = detail["PERCENTAGE"]
        position = detail["PLACE"]
        place = ordinal(position)

        this_partner_name = ""
        partner_names = {
            player["NATIONAL_ID_NUMBER"]: player["PLAYER_NAME"].title()
            for player in detail["PLAYER"]
        }

        for player in detail["PLAYER"]:
            player_system_number = player["NATIONAL_ID_NUMBER"]
            for partner_name in partner_names:
                if player_system_number != partner_name:
                    this_partner_name = partner_names[partner_name][:100]

            # We create records even for unregistered players, so they have a history when they eventually register
            if player_system_number:
                PlayerSummaryResult(
                    player_system_number=player_system_number,
                    results_file=results_file,
                    result_date=event_date,
                    position=position,
                    partner_or_team_name=this_partner_name,
                    percentage=percentage,
                    result_string=f"{place} in {event_name} at {results_file.organisation}",
                    event_name=event_name,
                ).save()
