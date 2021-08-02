from django.core.management.base import BaseCommand

from accounts.models import User
from organisations.models import Organisation


class Command(BaseCommand):
    """
    Run this before setting up any clubs or states. If the pk is not 1 then change the
    settings.py to have the actual pk. Cleaner to keep it as 1 though.
    """

    def CreateClubs(
        self,
        org_id,
        name,
        address1,
        address2,
        address3,
        state,
        postcode,
        type,
        secretary,
    ):

        if not Organisation.objects.filter(org_id=org_id).exists():

            org = Organisation(
                org_id=org_id,
                name=name,
                address1=address1,
                address2=address2,
                suburb=address3,
                state=state,
                type=type,
                postcode=postcode,
                secretary=secretary,
            )
            org.save()
            self.stdout.write(
                self.style.SUCCESS(
                    "Successfully created new org - %s %s" % (org_id, name)
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("%s org already exists - ok" % name))

    def handle(self, *args, **options):
        print("Creating ABF.")
        secretary = User.objects.get(pk=1)
        self.CreateClubs(
            0,
            "ABF",
            "PO Box 397",
            None,
            "Fyshwick",
            "ACT",
            "2609",
            "National",
            secretary,
        )
