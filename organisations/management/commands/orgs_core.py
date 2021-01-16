""" management command functions for Orgs """

from organisations.models import Organisation


def create_org(self, org_id, name, address1, address2, address3, state, postcode, type):

    org = Organisation.objects.filter(org_id=org_id).first()

    if org:
        if org.name != name:
            self.stdout.write(
                self.style.ERROR("ERROR! id Already taken by: %s" % org.name)
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("%s org already exists - ok" % org.name)
            )
    else:
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
            self.style.SUCCESS("Successfully created new org - %s %s" % (org_id, name))
        )
    return org
