from django.core.management.base import BaseCommand

from rbac.management.commands.rbac_core import (
    create_RBAC_admin_group,
    create_RBAC_admin_tree,
    create_RBAC_default,
    create_RBAC_action,
    super_user_list,
)
from rbac.core import (
    rbac_add_user_to_admin_group,
    rbac_add_role_to_admin_group,
    rbac_create_group,
    rbac_add_role_to_group,
    rbac_add_user_to_group,
)
from organisations.models import Organisation
from accounts.models import User

""" Create static within RBAC for Organisations

    Creates an admin group for every club with a corresponding place in the
    tree and rights to manage payments.

    Also creates the security to manage editing club details

"""


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Running add_rbac_static_orgs")
        su_list = super_user_list(self)

        # Edit club details permissions
        create_RBAC_default(self, "orgs", "org", "Block")
        create_RBAC_default(self, "orgs", "admin", "Block")
        create_RBAC_action(
            self,
            "orgs",
            "org",
            "edit",
            "Has the ability to edit details relating to the specified organisation.",
        )

        create_RBAC_action(
            self,
            "orgs",
            "admin",
            "edit",
            "Has the ability to perform global org admin changes like adding clubs.",
        )

        # Manage members of clubs
        create_RBAC_default(self, "orgs", "members", "Block")
        create_RBAC_action(
            self,
            "orgs",
            "member",
            "edit",
            "Has the ability to change memberships for the specified organisation.",
        )

        group = create_RBAC_admin_group(
            self,
            "admin.orgs.abf.clubs",
            "edit-orgs",
            "Group for admins who can grant access to edit orgs.",
        )
        create_RBAC_admin_tree(self, group, "admin.orgs.abf.clubs.edit-orgs")

        for user in su_list:
            rbac_add_user_to_admin_group(user, group)

        rbac_add_role_to_admin_group(group, app="orgs", model="org")
        rbac_add_role_to_admin_group(group, app="orgs", model="members")

        # Create groups for states to administer clubs
        # for each club, org.parent points to a state that can control it

        # Defaults
        create_RBAC_default(self, "orgs", "state", "Block")

        # Only need one action - edit
        create_RBAC_action(
            self,
            "orgs",
            "state",
            "edit",
            "State level ability to create/edit/delete clubs.",
        )

        group = rbac_create_group(
            "rbac.orgs.abf.abf_roles",
            "organisation_admin",
            "Add/Delete/Edit Clubs",
        )
        for user in su_list:
            rbac_add_user_to_group(user, group)
        rbac_add_role_to_group(
            group, app="orgs", model="admin", action="edit", rule_type="Allow"
        )
        rbac_add_role_to_group(
            group, app="orgs", model="members", action="edit", rule_type="Allow"
        )

        # We will add the rest of the RBAC rules in create_states so it is in once place plus we need the states to
        # exist before we can manipulate them.
