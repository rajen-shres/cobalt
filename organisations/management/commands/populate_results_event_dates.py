"""
Script to populate missing event_dates on the ResultsFile table from the USEBIO files
"""

from django.core.management.base import BaseCommand
from django.utils.datetime_safe import datetime

from results.models import ResultsFile

from results.views.usebio import parse_usebio_file


class Command(BaseCommand):
    help = "Populate missing event_dates on the ResultsFile table from the USEBIO files"

    def update_result(self, results_file):
        """Update the event_date on this result"""

        print(f"   Filename '{results_file.results_file.name}'")

        try:
            usebio = parse_usebio_file(results_file)["EVENT"]
            event_date_str = usebio.get("DATE")

        except FileNotFoundError:
            print("    ERROR - File not found")
            event_date_str = ""

        except Exception as e:
            print(f"    ERROR - Excpetion while parsing file {e}")
            event_date_str = ""

        # Try to get the date from the file (being consistent with player records
        try:
            event_date = datetime.strptime(event_date_str, "%d/%m/%Y").date()
        except ValueError:
            try:
                event_date = datetime.strptime(event_date_str, "%d-%m-%Y").date()
            except ValueError:
                event_date = None

        print(f"   {event_date}")

        if event_date is not None:
            results_file.event_date = event_date
            results_file.save()

    def handle(self, *args, **options):

        incomplete_results = ResultsFile.objects.filter(event_date=None)

        for result in incomplete_results:
            print(f"Processing {result.description} ")
            self.update_result(result)
