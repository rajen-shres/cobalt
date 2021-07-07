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
from support.models import NotifyUserByType


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Running add_rbac_static_support")
        create_RBAC_default(self, "support", "helpdesk", "Block")
        create_RBAC_action(
            self,
            "support",
            "helpdesk",
            "edit",
            "Can view and change helpdesk tickets",
        )

        # Create admin groups
        user = User.objects.filter(username="Mark").first()
        user2 = User.objects.filter(username="518891").first()
        group = create_RBAC_admin_group(
            self,
            "admin.orgs.abf.abf_roles",
            "helpdesk",
            "Group to manage access to the helpdesk for the ABF",
        )
        create_RBAC_admin_tree(self, group, "rbac.orgs.abf")
        rbac_add_user_to_admin_group(group, user)
        rbac_add_user_to_admin_group(group, user2)
        rbac_add_role_to_admin_group(group, app="support", model="helpdesk")

        # Create normal RBAC group for helpdesk

        group = rbac_create_group(
            "rbac.orgs.abf.abf_roles",
            "helpdesk_staff",
            "Access to the Helpdesk",
        )
        rbac_add_user_to_group(user, group)
        rbac_add_user_to_group(user2, group)
        rbac_add_role_to_group(
            group, app="support", model="helpdesk", action="all", rule_type="Allow"
        )

        # Now add users to static (non-RBAC)

        if not NotifyUserByType.objects.filter(staff=user).exists():
            NotifyUserByType(staff=user, incident_type="All").save()

        if not NotifyUserByType.objects.filter(staff=user2).exists():
            NotifyUserByType(staff=user2, incident_type="All").save()
