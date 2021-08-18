from django.core.management.base import BaseCommand

from post_office import mail


class Command(BaseCommand):
    def handle(self, *args, **options):
        mail.send(
            ["m@rkguthrie.com"],
            "mailtest@amyabf.com.au",
            subject="Welcome!",
            message="Welcome home!",
            html_message="Welcome home, <b>barry</b>!",
            headers={"COBALT_ID": "fishcake"},
        )
        this_mail = mail.create(
            sender="mailtest@myabf.com.au",
            recipients=["m@rkguthrie.com"],
            subject="Hello",
            message="hello",
            html_message="<h1>Hello</h1>",
            priority="now",
        )

        this_mail.headers = {"COBALT_ID": this_mail.id}

        this_mail.dispatch()
