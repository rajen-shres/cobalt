import logging
import xml

from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404

from organisations.decorators import check_club_menu_access
from organisations.forms import ResultsFileForm
from organisations.views.club_menu import tab_results_htmx
from results.models import ResultsFile
from results.views.usebio import (
    parse_usebio_file,
    create_player_records_from_usebio_format_pairs,
)

logger = logging.getLogger("cobalt")


@check_club_menu_access(check_sessions=True)
def upload_results_file_htmx(request, club):
    """Upload a new email attachment for a club
    Use the HTMX hx-trigger response header to tell the browser about it
    """

    form = ResultsFileForm(request.POST, request.FILES)
    if form.is_valid():
        results_file = form.save(commit=False)

        # Add data
        results_file.organisation = club
        results_file.uploaded_by = request.user
        results_file.save()

        # Try to parse the file
        try:
            usebio = parse_usebio_file(results_file)

        except xml.parsers.expat.ExpatError:
            results_file.delete()
            logger.error(f"Invalid file format - user: {request.user}")
            return tab_results_htmx(request, message="Invalid file format")

        results_file.description = usebio.get("EVENT").get("EVENT_DESCRIPTION")
        results_file.save()

        # Create the player records so people know the results are there
        create_player_records_from_usebio_format_pairs(results_file, usebio)

    return tab_results_htmx(request, message="New results successfully uploaded")


@check_club_menu_access(check_sessions=True)
def toggle_result_publish_state_htmx(request, club):
    """change to published / pending"""

    results_file_id = request.POST.get("results_file_id")
    results_file = get_object_or_404(ResultsFile, pk=results_file_id)

    if results_file.organisation != club:
        return HttpResponse("Access Denied")

    if results_file.status == ResultsFile.ResultsStatus.PENDING:
        results_file.status = ResultsFile.ResultsStatus.PUBLISHED
        message = f"{results_file.description} published, and players emailed (not implemented yet)"
    else:
        results_file.status = ResultsFile.ResultsStatus.PENDING
        message = f"{results_file.description} changed to pending"

    results_file.save()

    return tab_results_htmx(request, message=message)


@check_club_menu_access(check_sessions=True)
def delete_results_file_htmx(request, club):
    """delete a results file"""

    results_file_id = request.POST.get("results_file_id")
    results_file = get_object_or_404(ResultsFile, pk=results_file_id)

    if results_file.organisation != club:
        return HttpResponse("Access Denied")

    results_file.delete()

    return tab_results_htmx(request, message="Deleted")
