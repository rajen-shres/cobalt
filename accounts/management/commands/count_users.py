from django.core.management.base import BaseCommand
from accounts.models import User


class Command(BaseCommand):
    def handle(self, *args, **options):

        count = User.objects.count()

        print(f"There are {count:,} users")
