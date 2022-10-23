""" Add global things that don't fit in any module """
from django.core.management.base import BaseCommand
from rbac.management.commands.rbac_core import (
    create_rbac_together,
)


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Running add_rbac_static_global")

        # settings such as maintenance mode
        create_rbac_together(
            self,
            app="system",
            model="admin",
            action_dict={"edit": "Allows a user to manage system-wide settings"},
            admin_tree="admin.abf.system-wide",
            admin_name="admins",
            admin_description="Group to create users who can manage system settings",
            group_tree="rbac.orgs.abf.abf_roles",
            group_name="system_wide",
            group_description="Ability to change settings",
        )
