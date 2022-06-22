from django.core.management.base import BaseCommand

from support.helpdesk import close_old_tickets


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Running close_old_helpdesk_tickets")
        close_old_tickets()
