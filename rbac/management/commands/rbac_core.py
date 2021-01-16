""" Functions to manipulate RBAC from command scripts """

from rbac.models import (
    RBACModelDefault,
    RBACAppModelAction,
    RBACAdminTree,
    RBACAdminGroup,
)
from django.db.utils import IntegrityError


def create_RBAC_default(self, app, model, default_behaviour="Block"):
    """ create a default behaviour for an app.model

    Args:
        self(object): the calling management object
        app(str): the application
        mdeol(str): the model
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
    """ create an action for an app.model

    Args:
        self(object): the calling management object
        app(str): the application
        model(str): the model
        action(str): action to add
        description(str): what this is for

    Returns: Nothing
    """

    if not RBACAppModelAction.objects.filter(
        app=app, model=model, valid_action=action
    ).exists():
        r = RBACAppModelAction(
            app=app, model=model, valid_action=action, description=description
        )
        r.save()
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
    """ create a tree entry for admin

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
    """ create an admin group

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
