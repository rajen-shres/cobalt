import html
import re

import requests

from accounts.models import User
from cobalt.settings import GLOBAL_MPSERVER, MP_USE_FILE


def masterpoint_query_list(query):
    """Generic function to talk to the masterpoints SQL Server and return data as a list"""

    url = f"{GLOBAL_MPSERVER}/{query}"

    try:
        response = requests.get(url, timeout=10).json()
    except Exception as exc:
        print(exc)
        response = []

    return response


def masterpoint_query_row(query):
    """Generic function to get first row from query"""

    ret = masterpoint_query_list(query)
    if ret:
        return ret[0]
    return None


def mp_file_grep(pattern):
    with open("media/masterpoints/MPData.csv", "r", encoding="utf-8") as mp_file:
        for line in mp_file:
            if re.search(pattern, line):
                return line.split(",")


class MasterpointFactory:
    """Abstract class for accessing masterpoint data"""

    class Meta:
        abstract = True

    def get_masterpoints(self, system_number):
        """Get total masterpoints"""

    def system_number_lookup(self, system_number):
        """Look up the system number and return name"""


class MasterpointDB(MasterpointFactory):
    """Concrete implementation of a masterpoint factory using a database to get the data"""

    def get_masterpoints(self, system_number):
        summary = masterpoint_query_row(f"mps/{system_number}")
        if summary:
            points = summary["TotalMPs"]
            rank = summary["RankName"] + " Master"
        else:
            points = "Not found"
            rank = "Not found"

        return {"points": points, "rank": rank}

    def system_number_lookup(self, system_number):
        result = masterpoint_query_row(f"id/{system_number}")
        if result:
            if User.objects.filter(
                system_number=system_number, is_active=True
            ).exists():
                return "Error: User already registered"
            if result["IsActive"] == "Y":
                # only use first name from given names
                given_name = result["GivenNames"].split(" ")[0]
                surname = result["Surname"]
                return html.unescape(f"{given_name} {surname}")


class MasterpointFile(MasterpointFactory):
    """Concrete implementation of a masterpoint factory using a file to get the data"""

    def get_masterpoints(self, system_number):

        pattern = f"{int(system_number):07}"
        result = mp_file_grep(pattern)

        if result:
            points = result[7]
            rank = f"{result[19]} Master"
        else:
            points = "Not found"
            rank = "Not found"

        return {"points": points, "rank": rank}

    def system_number_lookup(self, system_number):

        pattern = f"{int(system_number):07}"
        result = mp_file_grep(pattern)

        if result:
            if User.objects.filter(
                system_number=system_number, is_active=True
            ).exists():
                return "Error: User already registered"
            if result[6] == "Y":
                # only use first name from given names
                given_name = result[2].split(" ")[0]
                surname = result[1]
                return html.unescape(f"{given_name} {surname}")

        return "Error: Inactive or invalid number"


def masterpoint_factory_creator():

    if MP_USE_FILE:
        return MasterpointFile()
    else:
        return MasterpointDB()
