import shutil
import xml
from glob import glob

from django.urls import reverse

from cobalt.settings import MEDIA_ROOT
from organisations.models import Organisation
from results.models import ResultsFile
from results.views.usebio import (
    parse_usebio_file,
    players_from_usebio,
    boards_from_usebio,
)
from tests.test_manager import CobaltTestManagerUnit

TEST_FILE_PATH = "results/tests/test_files"
TEST_FILE_OVERWRITE = "results_test_file.xml"


def results_file_url_checker(results_file, manager, test_name, test_description):
    """Check urls on results files"""

    # results summary url
    url = reverse(
        "results:usebio_mp_pairs_results_summary_view",
        kwargs={"results_file_id": results_file.id},
    )
    response = manager.client.get(url)
    if response.status_code != 200:
        manager.save_results(
            status=False,
            test_name=test_name,
            test_description=test_description,
            output=f"Failed at step 2 - finding the summary url. Tried to access {url}. RC={response.status_code}",
        )

    manager.save_results(
        status=True,
        test_name=test_name,
        test_description=test_description,
        output=f"Successfully accessed {url}. RC={response.status_code}",
    )

    # Now try to access the user results
    players = players_from_usebio(results_file)
    players_pass = []
    players_fail = []
    for player in players:
        url = reverse(
            "results:usebio_mp_pairs_details_view",
            kwargs={"results_file_id": results_file.id, "pair_id": player},
        )
        response = manager.client.get(url)

        print(f"Checking {url}...")

        if response.status_code == 200:
            players_pass.append(player)
        else:
            players_fail.append(player)

    manager.save_results(
        status=not players_fail,
        test_name=f"{test_name} - player summary",
        test_description=test_description,
        output=f"Step 3 - user summary pages. Errors on {players_fail}. Succeeded on {players_pass}",
    )

    # Now do the travellers
    boards = boards_from_usebio(results_file)
    boards_pass = []
    boards_fail = []
    for player in players:
        for board in boards:
            url = reverse(
                "results:usebio_mp_pairs_board_view",
                kwargs={
                    "results_file_id": results_file.id,
                    "pair_id": player,
                    "board_number": board,
                },
            )
            response = manager.client.get(url)

            print(f"Checking {url}...")

            if response.status_code == 200:
                boards_pass.append(f"{player} - {board}")
            else:
                boards_fail.append(f"{player} - {board}")

    manager.save_results(
        status=not boards_fail,
        test_name=f"{test_name} - travellers",
        test_description=test_description,
        output=f"Step 4 - travellers pages. Errors on {boards_fail}. Succeeded on {boards_pass}",
    )


def results_file_handler(club, file, manager):
    """helper for creating and testing a results file. This part creates it and then calls a function above to test
    it"""

    # Copy file to media, we just overwrite it each time
    shutil.copyfile(file, f"{MEDIA_ROOT}{TEST_FILE_OVERWRITE}")

    # create results_file record
    results_file = ResultsFile(
        results_file=TEST_FILE_OVERWRITE, organisation=club, uploaded_by=manager.alan
    )
    results_file.save()

    test_name = f"Results file test - {file}"
    test_description = ("Add file to database and check URLS work for results viewing",)

    # Try to parse the file
    try:
        usebio = parse_usebio_file(results_file)

    except xml.parsers.expat.ExpatError:
        results_file.delete()
        manager.save_results(
            status=False,
            test_name=test_name,
            test_description=test_description,
            output="Failed at upload stage Step 1 - could not parse XML file",
        )
        return

    results_file.description = usebio.get("EVENT").get("EVENT_DESCRIPTION")
    results_file.save()

    # now test it
    results_file_url_checker(results_file, manager, test_name, test_description)


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

        return

        club = Organisation.objects.get(pk=1)
        self.manager.login_test_client(self.manager.alan)

        for file in glob(f"{TEST_FILE_PATH}/*.*"):
            results_file_handler(club, file, self.manager)
