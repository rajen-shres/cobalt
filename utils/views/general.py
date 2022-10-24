import csv

import requests
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from geopy import Nominatim


@login_required()
def geo_location(request, location):
    """return lat and long for a text address"""

    try:
        geolocator = Nominatim(user_agent="cobalt")
        loc = geolocator.geocode(location)
        html = {"lat": loc.latitude, "lon": loc.longitude}
        data_dict = {"data": html}
        return JsonResponse(data=data_dict, safe=False)
    except:  # noqa E722
        return JsonResponse({"data": {"lat": None, "lon": None}}, safe=False)


def download_csv(self, request, queryset):
    """Copied from Stack Overflow - generic CSV download"""

    model = queryset.model
    model_fields = model._meta.fields + model._meta.many_to_many
    field_names = [field.name for field in model_fields]

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="export.csv"'

    # the csv writer
    writer = csv.writer(response)
    # Write a first row with header information
    writer.writerow(field_names)
    # Write data rows
    for row in queryset:
        values = []
        for field in field_names:
            value = getattr(row, field)

            values.append(value)
        writer.writerow(values)

    return response


def masterpoint_query(query):
    """Generic function to talk to the masterpoints server and return data

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
