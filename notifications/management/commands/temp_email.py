from django.core.management.base import BaseCommand
from django.template.loader import get_template
from post_office import mail as po_mail

from notifications.views import send_cobalt_email_with_template, create_rbac_batch_id


class Command(BaseCommand):
    def handle(self, *args, **options):
        batch_id = create_rbac_batch_id("orgs.org.5.view")

        for name in [
            "brian",
            "alice",
            "colin",
            "fred",
            "eric",
            "andrew",
            "fiona",
            "tub",
        ]:

            context = {
                "name": name,
                "subject": "Something new",
                "title": f"This for {name}, good on ya",
                "email_body": "<h2>Hi</h2>I am some text and shit.<br><br>More here.",
                "additional_words": "And here is some more stuff",
                "link": "/events",
                "link_text": "click me",
                "box_colour": "danger",
            }

            send_cobalt_email_with_template(
                to_address="mark.guthrie@17ways.com.au",
                context=context,
                batch_id=batch_id,
            )
