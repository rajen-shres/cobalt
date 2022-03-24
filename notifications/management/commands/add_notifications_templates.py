from pathlib import Path

from django.core.management.base import BaseCommand
from post_office.models import EmailTemplate

ROOT = "notifications/templates/notifications/django_post_office_core_templates/"

SYSTEM_EMAIL_TEMPLATES = [
    (
        "default",
        "po_email_default.html",
        "This is the main system email with a button and link which are used if link is specified.",
    ),
    (
        "two headings",
        "po_email_with_two_headings.html",
        "System email with a heading and a sub-heading",
    ),
]


class Command(BaseCommand):
    """Load templates from Django templates dir into Django Post Office (update in case changed)

    Templates live in the ROOT directory defined above.

    """

    def handle(self, *args, **options):
        print("Running add_notifications_templates")

        for template in SYSTEM_EMAIL_TEMPLATES:
            short_name, filename, description = template
            name = f"system - {short_name}"
            html_content = Path(f"{ROOT}{filename}").read_text()

            email_template = EmailTemplate.objects.filter(name=name).first()

            if not email_template:
                email_template = EmailTemplate.objects.create(name=name)
                self.stdout.write(self.style.SUCCESS(f"Added new template: {name}"))

            email_template.subject = "{{ subject }}"
            email_template.html_content = html_content
            email_template.description = description
            email_template.save()

            self.stdout.write(self.style.SUCCESS(f"Updated template: {name}"))
