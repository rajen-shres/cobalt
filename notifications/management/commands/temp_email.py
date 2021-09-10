from django.core.management.base import BaseCommand
from django.template.loader import get_template
from post_office import mail as po_mail

from notifications.views import send_cobalt_email_with_template


class Command(BaseCommand):
    def handle(self, *args, **options):

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

            # po_mail.send(
            #     "mark.guthrie@17ways.com.au",
            #     "Dev Testing 5<donotreply@myabf.com.au>",
            #     template="system - button",
            #     context={"name": name},
            #     render_on_delivery=True,
            #     priority="medium",
            # )

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
                to_address="mark.guthrie@17ways.com.au", context=context
            )

        # from django.core.mail import EmailMultiAlternatives
        #
        # subject, body = "Hello", "Plain text body"
        # from_email, to_email = 'Dev Testing<donotreply@myabf.com.au>', 'm@rkguthrie.com'
        # email_message = EmailMultiAlternatives(subject, body, from_email, [to_email])
        # template = get_template('notifications/po_email_with_button.html', using='post_office')
        # context = {'name': 'Brian', 'link_text': "click me!"}
        # html = template.render(context)
        # # email_message.attach_alternative(html, 'text/html')
        # template.attach_related(email_message)
        # email_message.send()
