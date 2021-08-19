from django.core.management.base import BaseCommand

from post_office import mail

from notifications.models import Snooper


class Command(BaseCommand):
    def handle(self, *args, **options):

        this_mail = mail.create(
            sender="mailtest@myabf.com.au",
            recipients=["m@rkguthrie.com"],
            subject="Hello",
            message="hello",
            html_message="<h1>Hello</h1>",
            priority="now",
        )

        #    this_mail.headers = {"COBALT_ID": this_mail.id}

        this_mail.dispatch()

        Snooper(post_office_email=this_mail).save()
