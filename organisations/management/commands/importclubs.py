from django.core.management.base import BaseCommand
from organisations.models import Organisation


class Command(BaseCommand):
    """
    I need the masterpoints file ClubsData.csv to be in the support/files directory.
    You can get this from abfmasterpoints.com.au
    """

    def CreateClubs(
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
                    "Successfully created new club - %s %s" % (org_id, name)
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("%s club already exists - ok" % name))

    def handle(self, *args, **options):
        print("Running importclubs.")
        num = Organisation.objects.count()
        if num >= 200:
            self.stdout.write(
                self.style.SUCCESS("Plenty of test data already found %s rows" % num)
            )
            return
        first_line = True
        with open("support/files/ClubsData.csv") as f:
            for line in f:
                print(line)
                if first_line:
                    first_line = False
                    continue
                parts = line.strip().split(",")
                org_id = parts[0]
                name = parts[1]
                address1 = parts[2]
                address2 = parts[3]
                address3 = parts[4]
                state = parts[5].upper()
                postcode = parts[6]
                type = "Club"
                self.CreateClubs(
                    org_id, name, address1, address2, address3, state, postcode, type
                )
