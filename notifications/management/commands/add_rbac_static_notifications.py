from django.core.management.base import BaseCommand
from rbac.management.commands.rbac_core import (
    create_RBAC_action,
    create_RBAC_default,
    create_rbac_together,
)


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Running add_rbac_static_notifications")

        # basic events behaviours
        create_rbac_together(
            self,
            app="notifications",
            model="admin",
            action_dict={
                "view": "Allows a user to manage notifications such as emails"
            },
            admin_tree="admin.abf.notifications",
            admin_name="admins",
            admin_description="Group to create users who can manage notifications",
            group_tree="rbac.orgs.abf.abf_roles",
            group_name="email_view",
            group_description="Ability to see all messages in notifications",
        )

        # SMS notifications - call them realtime in case we move to an app later
        # We have a scorer role where they can send and view their own messages and an admin role to view all messages
        create_rbac_together(
            self,
            app="notifications",
            model="realtime_send",
            action_dict={
                "edit": "Allows a scorer to send and view real time messages such as SMS."
            },
            admin_tree="admin.abf.notifications",
            admin_name="realtime_admins",
            admin_description="Group to create users who can send realtime messages (eg SMS).",
            group_tree="rbac.orgs.abf.abf_roles",
            group_name="realtime_send",
            group_description="Ability to send realtime messages, eg SMS",
        )

        # Club comms roles
        create_RBAC_default(self, "notifications", "orgcomms", "Block")
        create_RBAC_action(
            self,
            "notifications",
            "orgcomms",
            "edit",
            "Allows a user to communicate on behalf of an org",
        )

        # member to member roles - these are dummy roles so we can use batch_ids to obscure a user's id
        create_RBAC_default(self, "notifications", "member_comms", "Block")
        create_RBAC_action(
            self,
            "notifications",
            "member_comms",
            "view",
            "Dummy role for member to member comms. Allows use of batch_ids to obscure member id",
        )

        # We don't create an ABF role for this as there isn't a scenario where an Admin would need to send email on
        # behalf of a club where the club couldn't just grant access normally.
