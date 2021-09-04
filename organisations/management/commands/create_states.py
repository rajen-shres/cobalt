""" Must run after add_rbac_static_orgs """

from django.core.management.base import BaseCommand

from accounts.models import User
from cobalt.settings import ABF_STATES
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


class Command(BaseCommand):
    def create_states(
        self,
        org_id,
        name,
        address1,
        address2,
        address3,
        state,
        postcode,
        org_type,
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
                type=org_type,
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
        print("Creating State Organisations.")

        secretary = User.objects.get(pk=1)

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
                secretary,
            )

        print("Setting up RBAC for states.")

        su_list = super_user_list(self)

        # Create RBAC group and admin group per state and grant access
        for state_id in ABF_STATES:
            state = ABF_STATES[state_id][0]

            # Get Cobalt organisation for this state body
            state_org = Organisation.objects.get(org_id=state_id)

            # RBAC
            qualifier = f"rbac.orgs.states.{state}"
            description = f"Club admins - add/delete/edit Clubs in {state}"

            group = rbac_create_group(qualifier, "club_admin", description)
            rbac_add_role_to_group(
                group,
                app="orgs",
                model="state",
                action="all",
                rule_type="Allow",
                model_id=state_id,
            )
            # We also give state admins membership rights for all clubs - too hard to filter to state level
            rbac_add_role_to_group(
                group,
                app="orgs",
                model="members",
                action="all",
                rule_type="Allow",
            )

            # Admin
            qualifier = f"admin.states.{state}"
            description = f"{state} Club Admins"

            group = create_RBAC_admin_group(self, qualifier, state, description)

            create_RBAC_admin_tree(self, group, f"{qualifier}.{state}")

            for user in su_list:
                rbac_add_user_to_admin_group(user, group)

            rbac_add_role_to_admin_group(
                group, app="orgs", model="state", model_id=state_org.id
            )
            rbac_add_role_to_admin_group(group, app="orgs", model="members")
