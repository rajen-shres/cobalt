""" Functions to manipulate RBAC from command scripts """
from accounts.models import User
from rbac.core import (
    rbac_add_role_to_admin_group,
    rbac_create_group,
    rbac_add_user_to_group,
    rbac_add_role_to_group,
    rbac_add_user_to_admin_group,
)
from rbac.models import (
    RBACModelDefault,
    RBACAppModelAction,
    RBACAdminTree,
    RBACAdminGroup,
)
from django.db.utils import IntegrityError


def super_user_list(self):
    """We use the same users for everything. Build list in one place"""

    # Currently Mark and Julian
    return User.objects.filter(username__in=["Mark", "518891"])


def create_RBAC_default(self, app, model, default_behaviour="Block"):
    """create a default behaviour for an app.model

    Args:
        self(object): the calling management object
        app(str): the application
        model(str): the model
        default_behaviour(str): Block or Allow

    Returns: Nothing
    """

    if not RBACModelDefault.objects.filter(app=app, model=model).exists():
        r = RBACModelDefault(app=app, model=model, default_behaviour=default_behaviour)
        r.save()
        self.stdout.write(
            self.style.SUCCESS("RBACModelDefault created for %s.%s" % (app, model))
        )
    else:
        self.stdout.write(self.style.SUCCESS("RBACModelDefault already exists - ok"))


def create_RBAC_action(self, app, model, action, description):
    """create an action for an app.model

    Args:
        self(object): the calling management object
        app(str): the application
        model(str): the model
        action(str): action to add
        description(str): what this is for

    Returns: Nothing
    """

    rbac_app_model_action, created = RBACAppModelAction.objects.get_or_create(
        app=app, model=model, valid_action=action
    )

    rbac_app_model_action.description = description

    rbac_app_model_action.save()

    if created:
        self.stdout.write(
            self.style.SUCCESS(
                "Added %s.%s.%s to RBACAppModelAction" % (app, model, action)
            )
        )
    else:
        self.stdout.write(
            self.style.SUCCESS(
                "%s.%s.%s already in RBACAppModelAction. Ok." % (app, model, action)
            )
        )


def create_RBAC_admin_tree(self, group, tree):
    """create a tree entry for admin

    Args:
        self(object): the calling management object
        group(RBACAdminGroup): admin group to add to
        tree(str): the tree

    Returns: Nothing
    """

    # This is weird. If we check for the row existing the same as the other methods
    # then it says it doesn't and then crashes creating it. Need to use try except.
    # Not a core part of the system so not going to worry about it.

    try:
        r = RBACAdminTree(group=group, tree=tree)
        r.save()
        self.stdout.write(
            self.style.SUCCESS("Added %s %s to RBACAdminTree" % (group, tree))
        )
    except IntegrityError:
        self.stdout.write(
            self.style.SUCCESS("%s %s already in RBACAdminTree. Ok." % (group, tree))
        )


def create_RBAC_admin_group(self, qualifier, item, description):
    """create an admin group

    Args:
        self(object): the calling management object
        qualifier(str): the area of the tree
        item(str): the name of the group
        description(str): description of function

    Returns: RBACAdminGroup
    """

    if not RBACAdminGroup.objects.filter(
        name_qualifier=qualifier, name_item=item
    ).exists():
        r = RBACAdminGroup(
            name_qualifier=qualifier, name_item=item, description=description
        )
        r.save()
        self.stdout.write(
            self.style.SUCCESS(
                "Added %s.%s %s to RBACAdminGroup" % (qualifier, item, description)
            )
        )
        return r

    else:
        r = RBACAdminGroup.objects.filter(
            name_qualifier=qualifier, name_item=item
        ).first()
        self.stdout.write(
            self.style.SUCCESS(
                "%s.%s already in RBACAdminGroup. Ok." % (qualifier, item)
            )
        )
        return r


def create_rbac_together(
    self,
    app,
    model,
    action_dict,
    admin_tree,
    admin_name,
    admin_description,
    group_tree=None,
    group_name=None,
    group_description=None,
    default="Block",
):
    """In management commands we often do the same thing repeatedly - create the defaults, create the admin
    group, create the group. This does it as a single command.

    Args:

        self(object): Management object, used so we can do nice printing etc. Legacy from when these functions lived in the class
        app(str): Name of the application e.g. Notifications
        model(str): Model for this application e.g. admin
        action_dict(dict): Dictionary of actions and descriptions. e.g. {"view": "Users an view this thing"}.
        admin_tree(str): Path in tree for admin group
        admin_name(str): Name for admin group
        admin_description(str): Description for admin group
        group_tree(str): Path in tree for group
        group_name(str): Name for group
        group_description(str): Description for group
        default(str): "Block" or "Allow", defaults to Block.

    """
    # Get standard list of super users who get access automatically
    su_list = super_user_list(self)

    # Create the RBAC default
    create_RBAC_default(self, app, model, default)

    # Create the actions
    for action_item in action_dict:
        create_RBAC_action(
            self,
            app,
            model,
            action_item,
            action_dict[action_item],
        )

    # Create admin group
    admin_group = create_RBAC_admin_group(
        self, admin_tree, admin_name, admin_description
    )

    # Create tree - should really be part of the call above
    create_RBAC_admin_tree(self, admin_group, admin_tree)

    for user in su_list:
        rbac_add_user_to_admin_group(user, admin_group)

    # Add the role to the admin group
    rbac_add_role_to_admin_group(admin_group, app=app, model=model)

    # Add the normal RBAC group if required
    if group_tree:
        group = rbac_create_group(group_tree, group_name, group_description)

        # Put usual suspects in group
        for user in su_list:
            rbac_add_user_to_group(user, group)

        # Add all actions to group
        for action_item in action_dict:
            rbac_add_role_to_group(
                group, app=app, model=model, action=action_item, rule_type="Allow"
            )
