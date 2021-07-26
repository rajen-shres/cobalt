from django.core.management.base import BaseCommand
from rbac.management.commands.rbac_core import (
    create_RBAC_admin_group,
    create_RBAC_admin_tree,
    super_user_list,
)
from rbac.core import rbac_add_user_to_admin_group, rbac_add_role_to_admin_group
from organisations.models import Organisation
from accounts.models import User

""" Create static within RBAC for Organisations

    Creates a super admin group
    tree and rights to manage tree from top level.


"""


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Running add_superadmin")
        su_list = super_user_list(self)
        super_group = create_RBAC_admin_group(self, "admin", "", "Super admin group")
        create_RBAC_admin_tree(self, super_group, "rbac")
        for user in su_list:
            rbac_add_user_to_admin_group(super_group, user)
            # add to global payment manage
            rbac_add_role_to_admin_group(super_group, app="payments", model="manage")
