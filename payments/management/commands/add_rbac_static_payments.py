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
        print("Running add_rbac_static_payments")
        create_RBAC_default(self, "payments", "manage", "Block")
        create_RBAC_action(
            self,
            "payments",
            "manage",
            "view",
            "Can view payments information for the specified organisation.",
        )
        create_RBAC_action(
            self,
            "payments",
            "manage",
            "edit",
            "Can change payments information for the specified organisation.",
        )
        create_RBAC_default(self, "payments", "global", "Block")
        create_RBAC_action(
            self,
            "payments",
            "global",
            "view",
            "View access to the central payments functions.",
        )
        create_RBAC_action(
            self,
            "payments",
            "global",
            "edit",
            "Ability to perform central payments functions such as adjustments and settlements.",
        )

        # Create admin groups for payments global
        user = User.objects.filter(username="Mark").first()
        user2 = User.objects.filter(username="518891").first()
        group = create_RBAC_admin_group(
            self,
            "admin.orgs.abf.abf_roles",
            "payments",
            "Group to manage access to payments for the ABF",
        )
        create_RBAC_admin_tree(self, group, "rbac.orgs.abf")
        rbac_add_user_to_admin_group(group, user)
        rbac_add_user_to_admin_group(group, user2)
        rbac_add_role_to_admin_group(group, app="payments", model="global")

        # Create normal RBAC group for payments Global

        group = rbac_create_group(
            "rbac.orgs.abf.abf_roles",
            "payments_officers",
            "Management of payments for the ABF",
        )
        rbac_add_user_to_group(user, group)
        rbac_add_role_to_group(
            group, app="payments", model="global", action="all", rule_type="Allow"
        )

        group = rbac_create_group(
            "rbac.orgs.abf.abf_roles",
            "payments_view",
            "Read only access to payments for the ABF",
        )
        rbac_add_user_to_group(user, group)
        rbac_add_user_to_group(user2, group)
        rbac_add_role_to_group(
            group, app="payments", model="global", action="view", rule_type="Allow"
        )
