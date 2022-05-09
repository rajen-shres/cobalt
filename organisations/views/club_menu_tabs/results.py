from django.http import HttpResponse
from django.shortcuts import render

from organisations.decorators import check_club_menu_access
from organisations.forms import ResultsFileForm
from results.models import ResultsFile
from results.views.usebio import parse_usebio_file


@check_club_menu_access(check_sessions=True)
def upload_results_file_htmx(request, club):
    """Upload a new email attachment for a club
    Use the HTMX hx-trigger response header to tell the browser about it
    """

    form = ResultsFileForm(request.POST, request.FILES)
    if form.is_valid():
        results_file = form.save(commit=False)
        results_file.organisation = club
        results_file.uploaded_by = request.user
        results_file.save()
        usebio = parse_usebio_file(results_file)
        results_file.description = usebio.get("EVENT").get("EVENT_DESCRIPTION")
        results_file.save()

    return HttpResponse("ok")
