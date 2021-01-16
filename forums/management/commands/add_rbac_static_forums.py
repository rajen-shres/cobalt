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
)
from accounts.models import User


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Running add_rbac_static_forums")

        # basic forums behaviours
        create_RBAC_default(self, "forums", "forum", "Allow")
        create_RBAC_default(self, "forums", "moderate", "Block")
        create_RBAC_action(
            self,
            "forums",
            "forum",
            "create",
            "Can create a Post in the specified forum.",
        )

        create_RBAC_action(
            self,
            "forums",
            "forum",
            "view",
            "Can view a Post including Replies and Comments in the specified forum.",
        )
        create_RBAC_action(
            self, "forums", "forum", "edit", "Can edit a Post in the specified forum."
        )
        create_RBAC_action(
            self,
            "forums",
            "moderate",
            "edit",
            "Has moderator access to the specified forum.",
        )

        # Forum admin
        create_RBAC_default(self, "forums", "admin", "Block")
        create_RBAC_action(
            self,
            "forums",
            "admin",
            "edit",
            "Has the ability to create, edit and delete forums.",
        )

        # add default admins and create tree and group
        # This lets us create admins who can create and delete forums
        user = User.objects.filter(username="Mark").first()
        user2 = User.objects.filter(username="518891").first()

        group = create_RBAC_admin_group(
            self,
            "admin.orgs.abf.forums",
            "admin",
            "Group to create users who can create, modify or delete forums",
        )
        create_RBAC_admin_tree(self, group, "rbac.orgs")
        create_RBAC_admin_tree(self, group, "rbac.modules.forums")
        rbac_add_user_to_admin_group(group, user)
        rbac_add_user_to_admin_group(group, user2)
        rbac_add_role_to_admin_group(group, app="forums", model="admin")

        # grant writes to forums.forum
        # This creates admins who can make people moderators or block forum access
        group = create_RBAC_admin_group(
            self,
            "admin.orgs.abf.forums",
            "moderators",
            "Group to create users who are moderators of forums or can hide forums",
        )
        # create group - won't duplicate if already exists
        create_RBAC_admin_tree(self, group, "rbac.orgs.abf.forums")
        rbac_add_user_to_admin_group(group, user)
        rbac_add_user_to_admin_group(group, user2)
        rbac_add_role_to_admin_group(group, app="forums", model="forum")
        rbac_add_role_to_admin_group(group, app="forums", model="moderate")
