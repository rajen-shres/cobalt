"""
One-off script to update OrganisationFrontPage entries to replace the '{{ congresses }}
tag with '{{ calendar }}' - for Sprint-48, COB-804
"""

from django.core.management.base import BaseCommand

from organisations.models import OrganisationFrontPage


class Command(BaseCommand):
    def handle(self, *args, **options):

        old_tag = "{{ CONGRESSES }}"
        new_tag = "{{ CALENDAR }}"

        front_pages = OrganisationFrontPage.objects.all()
        update_count = 0

        for front_page in front_pages:

            if old_tag in front_page.summary:
                front_page.summary = front_page.summary.replace(old_tag, new_tag)
                front_page.save()
                update_count += 1

        self.stdout.write(f"Updated {update_count} rows from {old_tag} to {new_tag}")
