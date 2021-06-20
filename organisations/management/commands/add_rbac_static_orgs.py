from django.core.management.base import BaseCommand
from rbac.management.commands.rbac_core import (
    create_RBAC_admin_group,
    create_RBAC_admin_tree,
    create_RBAC_default,
    create_RBAC_action,
)
from rbac.core import rbac_add_user_to_admin_group, rbac_add_role_to_admin_group
from organisations.models import Organisation
from accounts.models import User

""" Create static within RBAC for Organisations

    Creates an admin group for every club with a corresponding place in the
    tree and rights to manage payments.

    Also creates the security to manage editing club details

"""


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Running add_rbac_static_orgs")
        user = User.objects.filter(username="Mark").first()
        user2 = User.objects.filter(username="518891").first()
        orgs = Organisation.objects.all()
        for org in orgs:
            if org.type == "Club":
                state = "UNKNOWN" if org.state in ["", " "] else org.state
                item = org.name.replace(" ", "-")
                qualifier = f"admin.clubs.{state}"
                description = f"{org.name} Admins"

                group = create_RBAC_admin_group(self, qualifier, item, description)
                create_RBAC_admin_tree(self, group, f"{qualifier}.{item}")
                rbac_add_user_to_admin_group(group, user)
                rbac_add_user_to_admin_group(group, user2)
                rbac_add_role_to_admin_group(
                    group, app="payments", model="manage", model_id=org.id
                )

        # Edit club details permissions
        create_RBAC_default(self, "orgs", "org", "Block")
        create_RBAC_default(self, "orgs", "admin", "Block")
        create_RBAC_action(
            self,
            "orgs",
            "org",
            "edit",
            "Has the ability to edit details relating to the specified organisation.",
        )
        create_RBAC_action(
            self,
            "orgs",
            "org",
            "view",
            "Has the ability to view details relating to the specified organisation.",
        )
        create_RBAC_action(
            self,
            "orgs",
            "admin",
            "edit",
            "Has the ability to perform global org admin changes like adding clubs.",
        )
        group = create_RBAC_admin_group(
            self,
            "admin.orgs.abf.clubs",
            "edit-orgs",
            "Group for admins who can grant access to edit orgs.",
        )
        create_RBAC_admin_tree(self, group, "admin.orgs.abf.clubs.edit-orgs")
        rbac_add_user_to_admin_group(group, user)
        rbac_add_user_to_admin_group(group, user2)
        rbac_add_role_to_admin_group(group, app="orgs", model="org")
