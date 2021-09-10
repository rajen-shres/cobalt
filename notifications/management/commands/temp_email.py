from django.core.management.base import BaseCommand
from django.template.loader import get_template
from post_office import mail as po_mail


class Command(BaseCommand):
    def handle(self, *args, **options):

        po_mail.send(
            "mark.guthrie@17ways.com.au",
            "Dev Testing<donotreply@myabf.com.au>",
            template="system - button",
            context={"name": "Brian"},
            render_on_delivery=True,
            priority="now",
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
