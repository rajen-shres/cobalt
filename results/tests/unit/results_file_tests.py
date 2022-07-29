import xml

from django.urls import reverse

from organisations.models import Organisation
from results.models import ResultsFile
from results.views.usebio import parse_usebio_file
from tests.test_manager import CobaltTestManagerUnit, CobaltTestManagerIntegration
from django.test import Client


def results_file_url_checker(results_file, manager):
    """Check urls on results files"""

    # results summary
    url = reverse(
        "results:usebio_mp_pairs_results_summary_view",
        kwargs={"results_file_id": results_file.id},
    )
    response = manager.client.get(url)
    print(response.status_code)


def results_file_handler(club, file, manager):
    """helper for creating and testing a results file"""

    # create results_file record
    results_file = ResultsFile(
        results_file=file, organisation=club, uploaded_by=manager.alan
    )
    results_file.save()

    # Try to parse the file
    try:
        usebio = parse_usebio_file(results_file)

    except xml.parsers.expat.ExpatError:
        results_file.delete()
        manager.save_results(
            status=False,
            test_name=f"Results file test - {file}",
            test_description="Add file to database and check URLS work for results viewing",
            output="Failed at upload state - could not parse XML file",
        )
        return

    results_file.description = usebio.get("EVENT").get("EVENT_DESCRIPTION")
    results_file.save()

    # now test it
    results_file_url_checker(results_file, manager)


class DuplicateResultsUpload:
    """Fairly brutal. Upload Results files and check URLs don't break

    I originally tried to do this by manipulating the request object so we could call the _htmx
    view directly but this turned out to be too fiddly so we bypass the view and the form and
    create the model entry directly.

    """

    def __init__(self, manager: CobaltTestManagerUnit):
        self.manager = manager

    def duplicate_tests(self):
        """Main function"""

        file = "test_results.xml"
        club = Organisation.objects.get(pk=1)
        self.manager.login_test_client(self.manager.alan)

        results_file_handler(club, file, self.manager)
