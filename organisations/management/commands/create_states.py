from django.core.management.base import BaseCommand
from organisations.models import Organisation


class Command(BaseCommand):
    def CreateStates(
        self, org_id, name, address1, address2, address3, state, postcode, type
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
        print("Creating State Organisations.")
        self.CreateStates(1, "ACT", None, None, None, "ACT", None, "State")
        self.CreateStates(2, "NSW", None, None, None, "NSW", None, "State")
        self.CreateStates(3, "VIC", None, None, None, "VIC", None, "State")
        self.CreateStates(4, "QLD", None, None, None, "QLD", None, "State")
        self.CreateStates(5, "SA", None, None, None, "SA", None, "State")
        self.CreateStates(6, "WA", None, None, None, "WA", None, "State")
        self.CreateStates(7, "TAS", None, None, None, "TAS", None, "State")
        self.CreateStates(8, "NT", None, None, None, "NT", None, "State")
