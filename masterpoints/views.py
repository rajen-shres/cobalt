import calendar
import html
from datetime import datetime, date
from json import JSONDecodeError

import requests
from dateutil.relativedelta import relativedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect
from cobalt.settings import GLOBAL_MPSERVER
from .factories import masterpoint_factory_creator, masterpoint_query_list


#####
#
# This module is a little strange as it gets all of its data from
# an external source, not from our database.
#
# We use requests to access a node.js web service which connects
# to a SQL Server database. Confluence can tell you more
#
######


def masterpoint_query_local(query):
    """Generic function to talk to the masterpoints server and return data

    THIS IS A DUPLICATE OF THE FUNCTION IN UTILS/UTIL_VIEWS/MASTERPOINTS
    due to circular dependency problems.

    Takes in a SQLServer query e.g. "select count(*) from table"

    Returns an iterable, either an empty list or the response from the server.

    In case there is a problem connecting to the server, this will do everything it
    can to fail silently.

    """

    # Try to load data from MP Server

    try:
        response = requests.get(query, timeout=10).json()
    except Exception as exc:
        print(exc)
        response = []

    return response


def process_transactions(details, month, year):
    """
    Separate process and provisional details
    add formatting to the matchpoint numbers
    """
    provisional_details = []
    fixed_details = []
    month = int(month)
    year = int(year)
    for d in details:
        if d["PostingMonth"] >= month and d["PostingYear"] == year:
            provisional_details.append(d)
        else:
            fixed_details.append(d)
    return fixed_details, provisional_details


@login_required()
def masterpoints_detail(request, system_number=None, years=1, retry=False):
    if system_number is None:
        system_number = request.user.system_number

    # Get summary data
    qry = "%s/mps/%s" % (GLOBAL_MPSERVER, system_number)
    r = masterpoint_query_local(qry)

    if len(r) == 0:

        if retry:  # This isn't the first time we've been here
            messages.error(
                request,
                f"Masterpoints module unable to find entry for id: {system_number}",
                extra_tags="cobalt-message-error",
            )
            return redirect("dashboard:dashboard")

        # not found - set error and call this again
        messages.warning(
            request,
            f"No Masterpoints entry found for id: {system_number}",
            extra_tags="cobalt-message-warning",
        )
        return masterpoints_detail(request, retry=True)

    summary = r[0]

    # Set active to a boolean
    if summary["IsActive"] == "Y":
        summary["IsActive"] = True
    else:
        summary["IsActive"] = False

    # Get provisional month and year, anything this date or later is provisional
    #   qry = "%s/provisionaldate" % GLOBAL_MPSERVER
    #   data = requests.get(qry).json()[0]
    #   prov_month = "%02d" % int(data["month"])
    #   prov_year = data["year"]

    # Get home club name
    qry = "%s/club/%s" % (GLOBAL_MPSERVER, summary["HomeClubID"])
    club = requests.get(qry).json()[0]["ClubName"]

    # Get last year in YYYY-MM format
    dt = date.today()
    dt = dt.replace(year=dt.year - years)
    year = dt.strftime("%Y")
    month = dt.strftime("%m")

    # Get the detail list of recent activity
    qry = "%s/mpdetail/%s/postingyear/%s/postingmonth/%s" % (
        GLOBAL_MPSERVER,
        system_number,
        year,
        month,
    )
    details = requests.get(qry).json()

    counter = summary["TotalMPs"]  # we need to construct the balance to show
    gold = float(summary["TotalGold"])
    red = float(summary["TotalRed"])
    green = float(summary["TotalGreen"])

    # build list for the fancy chart at the top while we loop through.
    labels_key = []
    labels = []
    chart_green = {}
    chart_red = {}
    chart_gold = {}

    # build chart labels
    # go back a year then move forward
    rolling_date = datetime.today() + relativedelta(years=-years)

    for i in range(12 * years + 1):
        year = rolling_date.strftime("%Y")
        month = rolling_date.strftime("%m")
        labels_key.append("%s-%s" % (year, month))
        if years == 1:
            labels.append(rolling_date.strftime("%b"))
        else:
            labels.append(rolling_date.strftime("%b %Y"))
        rolling_date = rolling_date + relativedelta(months=+1)
        chart_gold["%s-%s" % (year, month)] = 0.0
        chart_red["%s-%s" % (year, month)] = 0.0
        chart_green["%s-%s" % (year, month)] = 0.0

    details, futureTrans = process_transactions(details, month, year)
    # todo: Tanmay to first extract details into two--> one current month next -- "future"
    # deatils will just have till current month future will go in provisional variable
    # loop through the details and augment the data to pass to the template
    # we are just adding running total data for the table of details
    for d in details:
        counter = counter - d["mps"]

        d["running_total"] = counter
        d["PostingDate"] = "%s-%02d" % (d["PostingYear"], d["PostingMonth"])
        d["PostingDateDisplay"] = "%s-%s" % (
            calendar.month_abbr[d["PostingMonth"]],
            d["PostingYear"],
        )

        # Its too slow to filter at the db so skip any month we don't want
        if not d["PostingDate"] in chart_gold:
            continue

        if d["MPColour"] == "Y":
            gold = gold - float(d["mps"])
            chart_gold[d["PostingDate"]] = chart_gold[d["PostingDate"]] + float(
                d["mps"]
            )
        elif d["MPColour"] == "R":
            red = red - float(d["mps"])
            chart_red[d["PostingDate"]] = chart_red[d["PostingDate"]] + float(d["mps"])
        elif d["MPColour"] == "G":
            green = green - float(d["mps"])
            chart_green[d["PostingDate"]] = chart_green[d["PostingDate"]] + float(
                d["mps"]
            )

    # fill in the chart data
    running_gold = float(summary["TotalGold"])
    gold_series = []
    for label in reversed(labels_key):
        running_gold = running_gold - chart_gold[label]
        gold_series.append(float("%.2f" % running_gold))
    gold_series.reverse()

    running_red = float(summary["TotalRed"])
    red_series = []
    for label in reversed(labels_key):
        running_red = running_red - chart_red[label]
        red_series.append(float("%.2f" % running_red))
    red_series.reverse()

    running_green = float(summary["TotalGreen"])
    green_series = []
    for label in reversed(labels_key):
        running_green = running_green - chart_green[label]
        green_series.append(float("%.2f" % running_green))
    green_series.reverse()

    chart = {
        "labels": labels,
        "gold": gold_series,
        "red": red_series,
        "green": green_series,
    }

    total = "%.2f" % (green + red + gold)
    green = "%.2f" % green
    red = "%.2f" % red
    gold = "%.2f" % gold

    bottom = {"gold": gold, "red": red, "green": green, "total": total}

    # Show bullets on lines or not
    if years > 2:
        show_point = "false"
    else:
        show_point = "true"

    # Show title every X points
    points_dict = {1: 1, 2: 3, 3: 5, 4: 12, 5: 12}
    try:
        points_every = points_dict[years]
    except KeyError:
        points_every = len(labels) - 1  # start and end only

    timescale = f"Last {years} years"

    if years == 1:
        timescale = "Last 12 Months"

    return render(
        request,
        "masterpoints/details.html",
        {
            "details": details,
            "summary": summary,
            "club": club,
            "chart": chart,
            "bottom": bottom,
            "show_point": show_point,
            "points_every": points_every,
            "system_number": system_number,
            "timescale": timescale,
        },
    )


@login_required()
def masterpoints_search(request):
    if request.method == "POST":
        system_number = request.POST["system_number"]
        last_name = request.POST["last_name"]
        first_name = request.POST["first_name"]
        if system_number:
            return redirect("view/%s/" % system_number)
        else:
            if not first_name:  # last name only
                matches = requests.get(
                    "%s/lastname_search/%s" % (GLOBAL_MPSERVER, last_name)
                ).json()
            elif not last_name:  # first name only
                matches = requests.get(
                    "%s/firstname_search/%s" % (GLOBAL_MPSERVER, first_name)
                ).json()
            else:  # first and last names
                matches = requests.get(
                    "%s/firstlastname_search/%s/%s"
                    % (GLOBAL_MPSERVER, first_name, last_name)
                ).json()
            if len(matches) == 1:
                system_number = matches[0]["ABFNumber"]
                return redirect("view/%s/" % system_number)
            else:
                return render(
                    request,
                    "masterpoints/masterpoints_search_results.html",
                    {"matches": matches},
                )
    else:
        return redirect("view/%s/" % request.user.system_number)


def system_number_lookup(request):
    """
    Called from the registration page. Takes in a system number and returns
    the member first and lastname or an error message.
    """

    if request.method == "GET":
        system_number = request.GET["system_number"]

        mp_source = masterpoint_factory_creator()
        return HttpResponse(mp_source.system_number_lookup(system_number))


def system_number_available(system_number):
    """
    Called from the registration page. Takes in a system number and returns
    True if number is valid and available
    """

    if not system_number.isdigit():
        return False

    mp_source = masterpoint_factory_creator()
    return mp_source.system_number_available(system_number)


def get_masterpoints(system_number):
    # Called from Dashboard

    mp_source = masterpoint_factory_creator()
    return mp_source.get_masterpoints(system_number)


def user_summary(system_number):
    """This is only here until we move masterpoints into Cobalt.
    It gets basic things such as home club and masterpoints.
    """

    # Get summary data
    qry = "%s/mps/%s" % (GLOBAL_MPSERVER, system_number)
    try:
        r = requests.get(qry).json()
    except (
        IndexError,
        requests.exceptions.InvalidSchema,
        requests.exceptions.MissingSchema,
        ConnectionError,
    ):
        r = []

    if not r:
        return None

    summary = r[0]

    # Set active to a boolean
    summary["IsActive"] = summary["IsActive"] == "Y"
    # Get home club name
    qry = "%s/club/%s" % (GLOBAL_MPSERVER, summary["HomeClubID"])
    summary["home_club"] = requests.get(qry).json()[0]["ClubName"]

    return summary


def get_abf_checksum(abf_raw: int) -> int:
    """Calculate the checksum for an ABF number given the raw number without the checksum

    Formula is:

    convert to 6 digit with trailing 0, e.g. 62024 becomes 062024
    total is 0th place x 7, 1st place x 6, 2nd place x 5 etc
    result = total mod 11
    if result = 0 checksum = 0
    else checksum = 11 - (result mod 11)

    """

    abf_string = f"{abf_raw:06d}"

    total = sum(int(val) * (7 - index) for index, val in enumerate(abf_string))

    mod = total % 11

    if mod == 0:
        return 0

    if mod == 1:
        return 1

    return 11 - mod


def abf_checksum_is_valid(abf_number: int) -> bool:
    """Takes an ABF number and confirms the number has a valid checksum. Doesn't check with the MPC to
    see if this is a valid number (not inactive, actually registered etc)."""

    this_checksum = abf_number % 10  # last digit
    true_checksum = get_abf_checksum(abf_number // 10)  # not last digit

    return this_checksum == true_checksum


def search_mpc_users_by_name(first_name_search, last_name_search):
    """search the masterpoint centre for users by first and last name"""

    # TODO: write a version of this for the other (text file) factory
    if not first_name_search:
        first_name_search = "None"
    if not last_name_search:
        last_name_search = "None"
    return masterpoint_query_list(
        f"firstlastname_search_active/{first_name_search}/{last_name_search}"
    )
