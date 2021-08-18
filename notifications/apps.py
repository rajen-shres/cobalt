import psycopg2
from django.apps import AppConfig
from django.db import ProgrammingError


class NotificationsConfig(AppConfig):
    name = "notifications"

    def ready(self):
        """Called when Django starts up

        We use the model EmailThread to record what email threads are running.
        After a restart we clear the table.

        For more information look in the docs at notifications_overview

        """

        # Can't import at top of file - Django won't be ready yet
        # Also if this is a clean install migrate won't have been run so catch an error and ignore

        try:
            from .models import EmailThread

            EmailThread.objects.all().delete()

        except (psycopg2.errors.UndefinedTable, ProgrammingError):
            # Should only happen if this a clean install (dev, test, UAT). Reasonably safe to ignore.
            pass

        from django.dispatch import receiver
        from django_ses.signals import send_received

        @receiver(send_received)
        def send_handler(sender, mail_obj, send_obj, raw_message, *args, **kwargs):

            print("Aardvark send_received", flush=True)
            headers = mail_obj["headers"]
            print("Headers\n", headers, flush=True)
            mail_id = None
            for header in headers:
                if header["name"] == "COBALT_ID":
                    mail_id = header["value"]
                    break
            print("Mail ID:", mail_id, flush=True)

            #            dict(email_message)

            #            email_id = headers["COBALT_ID"]
            #           print("Found Email ID:", email_id, flush=True)
            # print("sender")
            # print(sender, flush=True)
            # print("mail_obj")
            # print(mail_obj, flush=True)
            # print("send_obj")
            # print(send_obj, flush=True)
            # print("raw message", flush=True)
            # print(raw_message, flush=True)
