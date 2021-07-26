""" Must run after add_rbac_static_orgs """

from django.core.management.base import BaseCommand
from organisations.models import Organisation
from rbac.core import (
    rbac_create_group,
    rbac_add_role_to_group,
    rbac_add_user_to_admin_group,
    rbac_add_role_to_admin_group,
)
from rbac.management.commands.rbac_core import (
    create_RBAC_admin_group,
    create_RBAC_admin_tree,
    super_user_list,
)

ABF_STATES = {
    1801: ("BFACT", "ACT"),
    2001: ("NSWBA", "NSW"),
    3301: ("VBA", "VIC"),
    4501: ("QBA", "QLD"),
    5700: ("SABF", "SA"),
    6751: ("BAWA", "WA"),
    7801: ("TBA", "TAS"),
    8901: ("NTBA", "NT"),
}


class Command(BaseCommand):
    def create_states(
        self, org_id, name, address1, address2, address3, state, postcode, org_type
    ):

        if not Organisation.objects.filter(org_id=org_id).exists():

            org = Organisation(
                org_id=org_id,
                name=name,
                address1=address1,
                address2=address2,
                suburb=address3,
                state=state,
                type=org_type,
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
        for state in ABF_STATES:
            self.create_states(
                state,
                ABF_STATES[state][0],
                None,
                None,
                None,
                ABF_STATES[state][1],
                None,
                "State",
            )

        print("Setting up RBAC for states.")

        su_list = super_user_list(self)

        # Create RBAC group and admin group per state and grant access
        for state_id in ABF_STATES:
            state = ABF_STATES[state_id][0]

            # Get Cobalt organisation for this state body
            print(state, state_id)
            state_org = Organisation.objects.get(org_id=state_id)

            # RBAC
            qualifier = f"rbac.orgs.states.{state}"
            description = f"Club admins - add/delete/edit Clubs in {state}"

            group = rbac_create_group(qualifier, "club_admin", description)
            rbac_add_role_to_group(
                group, app="orgs", model="state", action="all", rule_type="Allow"
            )

            # Admin
            qualifier = f"admin.states.{state}"
            description = f"{state} Club Admins"

            group = create_RBAC_admin_group(self, qualifier, state, description)

            create_RBAC_admin_tree(self, group, f"{qualifier}.{state}")

            for user in su_list:
                rbac_add_user_to_admin_group(group, user)

            rbac_add_role_to_admin_group(
                group, app="orgs", model="state", model_id=state_org.id
            )
