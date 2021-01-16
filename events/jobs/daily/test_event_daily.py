from utils.views import CobaltBatch
from django_extensions.management.jobs import DailyJob
from time import sleep


class Job(DailyJob):
    help = "Test Daily Events job"

    def execute(self):

        batch = CobaltBatch(name="Job thing", schedule="Hourly", rerun=False)
        # instance is optional and only needed if you run multiple times per day

        if batch.start():
            # run your commands
            sleep(2)
            print("Batch job started")
            batch.finished(status="Success")

        else:
            print("Not started")
