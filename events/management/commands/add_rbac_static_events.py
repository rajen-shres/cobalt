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
    rbac_add_user_to_group,
    rbac_add_role_to_group,
)
from accounts.models import User


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Running add_rbac_static_events")

        # basic events behaviours
        create_RBAC_default(self, "events", "org", "Block")
        create_RBAC_action(
            self,
            "events",
            "org",
            "edit",
            "Allows a user to run a congress associated with the organisation specified.",
        )

        create_RBAC_default(self, "events", "global", "Block")
        create_RBAC_action(
            self,
            "events",
            "global",
            "edit",
            "Allows a user to manage Congress Masters",
        )

        # add admins and create tree and group
        # This lets us create admins who can create and delete forums
        su_list = super_user_list(self)

        group = create_RBAC_admin_group(
            self,
            "admin.abf.events",
            "orgs",
            "Group to create users who can create, modify or delete congresses",
        )
        create_RBAC_admin_tree(self, group, "admin.abf.events")
        for user in su_list:
            rbac_add_user_to_admin_group(user, group)
        rbac_add_role_to_admin_group(group, app="events", model="org")
        rbac_add_role_to_admin_group(group, app="events", model="global")
