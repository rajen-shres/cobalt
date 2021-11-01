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
    rbac_add_role_to_group, rbac_create_group,
)
from accounts.models import User


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Running add_rbac_static_club_sessions")

        create_RBAC_default(self, "club_sessions", "sessions", "Block")
        create_RBAC_action(
            self,
            "club_sessions",
            "sessions",
            "edit",
            "Allows a user to run a session for an organisation",
        )
        create_RBAC_default(self, "club_sessions", "sessions", "Block")
        create_RBAC_action(
            self,
            "club_sessions",
            "sessions",
            "view",
            "Allows a user to view a session for an organisation",
        )

        # add admins and create tree and group
        su_list = super_user_list(self)

        admin_group = create_RBAC_admin_group(
            self,
            "admin.abf.club_sessions",
            "admins",
            "Group to create users who can view or manage club sessions",
        )
        create_RBAC_admin_tree(self, admin_group, "admin.abf.club_sessions")
        for user in su_list:
            rbac_add_user_to_admin_group(user, admin_group)
        rbac_add_role_to_admin_group(admin_group, app="club_sessions", model="sessions")

        # Also give the su_list access to all clubs
        group = rbac_create_group(
            "rbac.orgs.abf.abf_roles",
            "club_sessions_edit",
            "Ability to edit any club session",
        )

        rbac_add_role_to_group(
            group=group,
            app="club_sessions",
            model="sessions",
            action="all",
            rule_type="Allow",
        )

        for user in su_list:
            rbac_add_user_to_group(user, group)