from django.core.management.base import BaseCommand
from rbac.management.commands.rbac_core import (
    create_RBAC_action,
    create_RBAC_default,
    create_RBAC_admin_group,
    create_RBAC_admin_tree,
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
        user = User.objects.filter(username="Mark").first()
        julian = User.objects.filter(system_number="518891").first()

        group = create_RBAC_admin_group(
            self,
            "admin.abf.notifications",
            "admins",
            "Group to create users who can manage notifications",
        )
        create_RBAC_admin_tree(self, group, "admin.abf.notifications")
        rbac_add_user_to_admin_group(group, user)
        rbac_add_role_to_admin_group(group, app="notifications", model="admin")

        group = rbac_create_group(
            "rbac.orgs.abf.abf_roles",
            "email_view",
            "Ability to see all messages in notifications",
        )
        rbac_add_user_to_group(user, group)
        rbac_add_user_to_group(julian, group)
        rbac_add_role_to_group(
            group, app="notifications", model="admin", action="view", rule_type="Allow"
        )
