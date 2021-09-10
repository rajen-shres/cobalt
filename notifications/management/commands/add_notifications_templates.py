from pathlib import Path

from django.core.management.base import BaseCommand
from post_office.models import EmailTemplate

from cobalt.settings import GLOBAL_TITLE

ROOT = "notifications/templates/notifications/"

templates = [
    ("button", "po_email_with_button.html"),
    #   ("no button", "po_email_without_button.html")
]


class Command(BaseCommand):
    """Load templates from Django templates dir into Django Post Office (update in case changed)"""

    def handle(self, *args, **options):
        print("Running add_notifications_templates")

        for template in templates:
            short_name, filename = template
            name = f"system - {short_name}"
            html_content = Path(f"{ROOT}{filename}").read_text()

            email_template = EmailTemplate.objects.filter(name=name).first()

            if not email_template:
                email_template = EmailTemplate.objects.create(name=name)
                self.stdout.write(self.style.SUCCESS(f"Added template: {name}"))

            email_template.subject = "{{ subject }}"
            email_template.content = "Hi {{ name }}, how are you feeling today?"
            email_template.html_content = html_content
            email_template.save()

            self.stdout.write(self.style.SUCCESS(f"Updated template: {name}"))
