from django.core.management.base import BaseCommand
from rbac.management.commands.rbac_core import (
    create_RBAC_action,
    create_RBAC_default,
    create_RBAC_admin_group,
    create_RBAC_admin_tree,
    super_user_list,
)
from rbac.core import (
    rbac_add_user_to_admin_group,
    rbac_add_role_to_admin_group,
    rbac_create_group,
    rbac_add_user_to_group,
    rbac_add_role_to_group,
)

from accounts.models import User


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Running add_rbac_static_notifications")

        # basic events behaviours
        create_RBAC_default(self, "notifications", "admin", "Block")
        create_RBAC_action(
            self,
            "notifications",
            "admin",
            "view",
            "Allows a user to manage notifications such as emails",
        )

        # add myself as an admin and create tree and group
        # This lets us create admins who can manage notifications
        su_list = super_user_list(self)

        group = create_RBAC_admin_group(
            self,
            "admin.abf.notifications",
            "admins",
            "Group to create users who can manage notifications",
        )
        create_RBAC_admin_tree(self, group, "admin.abf.notifications")
        for user in su_list:
            rbac_add_user_to_admin_group(user, group)
        rbac_add_role_to_admin_group(group, app="notifications", model="admin")

        group = rbac_create_group(
            "rbac.orgs.abf.abf_roles",
            "email_view",
            "Ability to see all messages in notifications",
        )

        for user in su_list:
            rbac_add_user_to_group(user, group)

        rbac_add_role_to_group(
            group, app="notifications", model="admin", action="view", rule_type="Allow"
        )

        # # Club comms roles
        # create_RBAC_default(self, "notifications", "orgcomms", "Block")
        # create_RBAC_action(
        #     self,
        #     "notifications",
        #     "orgcomms",
        #     "edit",
        #     "Allows a user to communicate on behalf of an org",
        # )

        # We don't create an ABF role for this as there isn't a scenario where an Admin would need to send email on
        # behalf of a club where the club couldn't just grant access normally.
