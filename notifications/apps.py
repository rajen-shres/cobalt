from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    name = "notifications"

    def ready(self):
        """Called when Django starts up

        We use the model EmailThread to record what email threads are running.
        After a restart we clear the table.

        For more information look in the docs at notifications_overview

        """

        # Can't import at top of file - Django won't be ready yet
        from .models import EmailThread

        print("Clearing any stale EmailThreads from database")
        EmailThread.objects.all().delete()
