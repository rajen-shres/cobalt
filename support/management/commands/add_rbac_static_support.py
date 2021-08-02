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
        su_list = super_user_list(self)
        group = create_RBAC_admin_group(
            self,
            "admin.orgs.abf.abf_roles",
            "helpdesk",
            "Group to manage access to the helpdesk for the ABF",
        )
        create_RBAC_admin_tree(self, group, "rbac.orgs.abf")
        for user in su_list:
            rbac_add_user_to_admin_group(user, group)
        rbac_add_role_to_admin_group(group, app="support", model="helpdesk")

        # Create normal RBAC group for helpdesk

        group = rbac_create_group(
            "rbac.orgs.abf.abf_roles",
            "helpdesk_staff",
            "Access to the Helpdesk",
        )
        for user in su_list:
            rbac_add_user_to_group(user, group)
        rbac_add_role_to_group(
            group, app="support", model="helpdesk", action="all", rule_type="Allow"
        )

        # Now add users to static (non-RBAC)

        for user in su_list:

            if not NotifyUserByType.objects.filter(staff=user).exists():
                NotifyUserByType(staff=user, incident_type="All").save()
