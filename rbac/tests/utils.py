import random
import string

from accounts.models import User
from rbac.core import rbac_create_group, rbac_add_user_to_group, rbac_add_role_to_group


def unit_test_rbac_add_role_to_user(
    user: User, app: str, model: str, action: str, model_id: int = None
):
    """Quick and dirty way to give a user a role. Used for general testing where you don't need to check all
    of the RBAC features, you just want a user to have a role"""

    name_qualifier = "".join(random.choices(string.ascii_uppercase, k=10))
    name_item = "".join(random.choices(string.ascii_uppercase, k=10))

    group = rbac_create_group(name_qualifier, name_item, "dummy desc")

    rbac_add_user_to_group(user, group)

    rbac_add_role_to_group(group, app, model, action, "Allow", model_id)
