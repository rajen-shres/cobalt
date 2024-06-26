"""
Public APIs to retrieve calendar information

June 2024 - Prooof on concept only, not production-ready code.
            paths in urls.py have been commented out.
"""

from django.http import JsonResponse
from django.shortcuts import render

from events.models import Congress
from organisations.models import Organisation


def _get_calendar_congresses(request):
    """
    Returns a query set of Congress objects based on the
    query parameters in the request.

    Supported query parameters are:
        org = <club_number>
    """

    qs = None

    org_id = request.GET.get("org", None)
    if org_id:
        org = Organisation.objects.filter(org_id=org_id).first()
        if org:
            qs = Congress.objects.filter(congress_master__org=org)

    return qs


def get_calendar_json(request):
    """
    Returns a json object of selected congress details
    """

    congresses = _get_calendar_congresses(request)

    dict = {}

    if congresses:

        congress_list = []

        for congress in congresses:
            congress_list.append(
                {
                    "name": congress.name,
                    "start_date": congress.start_date,
                    "end_date": congress.end_date,
                    "type": congress.congress_type,
                    "venue_type": congress.congress_venue_type,
                }
            )

        dict["congresses"] = congress_list

    return JsonResponse(dict)


def get_calendar_html(request):
    """
    Returns an html snippet of selected congress details
    """

    congresses = _get_calendar_congresses(request)

    return render(
        request,
        "events/api/get_calendar.html",
        {
            "congresses": congresses,
        },
    )
