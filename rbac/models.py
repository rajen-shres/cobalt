""" Role Based Access Control Application

    This handles the models for role based security for Cobalt.

    See `RBAC Overview`_ for more details.

    .. _RBAC Overview:
       ./rbac_overview.html
"""
from django.db import models
from accounts.models import User
from django.utils import timezone

RULE_TYPES = [("Allow", "Allow User Access"), ("Block", "Block User Access")]


class RBACGroup(models.Model):
    """ Group definitions """

    name_qualifier = models.CharField(max_length=50)
    """ eg "organisations.trumps" """

    name_item = models.CharField(max_length=50)
    """ chosen by the admin. appends onto name_qualifier """

    description = models.CharField(max_length=50)
    """ Free format decription """

    created_date = models.DateTimeField("Create Date", default=timezone.now)
    """ date created """

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, blank=True, null=True
    )
    """ Standard User object """

    class Meta:
        unique_together = ["name_qualifier", "name_item"]

    def __str__(self):
        return "%s.%s - %s" % (self.name_qualifier, self.name_item, self.description)

    @property
    def name(self):
        return "%s.%s" % (self.name_qualifier, self.name_item)


class RBACUserGroup(models.Model):
    """ Maps users to Groups """

    member = models.ForeignKey(User, on_delete=models.CASCADE)
    """ Standard User object """

    group = models.ForeignKey(RBACGroup, on_delete=models.CASCADE)
    """ RBAC Group """

    def __str__(self):
        return "%s - %s" % (self.group, self.member)


class RBACGroupRole(models.Model):
    """ Core model to map a group to a role. """

    group = models.ForeignKey(RBACGroup, on_delete=models.CASCADE)
    """ RBACGroup for this Role """

    app = models.CharField(max_length=15)
    """ Application level hierarchy """

    model = models.CharField(max_length=15)
    """ model level hierarchy """

    model_id = models.IntegerField(blank=True, null=True)
    """ Instance of model level hierarchy """

    action = models.CharField(max_length=15)
    """ What this role allows you to do here """

    rule_type = models.CharField(max_length=5, choices=RULE_TYPES, default="Allow")
    """ Rules can Allow or Block permissions """

    def __str__(self):
        return "%s - %s - %s" % (self.group, self.role, self.rule_type)

    @property
    def role(self):
        "Returns the role in dotted format including the action."
        if self.model_id:
            return "%s.%s.%s.%s" % (self.app, self.model, self.model_id, self.action)
        else:
            return "%s.%s.%s" % (self.app, self.model, self.action)

    @property
    def path(self):
        "Returns the role in dotted format excluding the action."
        if self.model_id:
            return "%s.%s.%s" % (self.app, self.model, self.model_id)
        else:
            return "%s.%s" % (self.app, self.model)


class RBACModelDefault(models.Model):
    """Default behaviour for a model. Some models (e.g. forums.forum) need a
    default of allowing users access unless explicitly blocked. Other models
    (e.g. organisations.Organisation) need a default behaviour of blocking unless
    explicitly allowed."""

    app = models.CharField(max_length=15)
    """ Application level hierarchy """

    model = models.CharField(max_length=15)
    """ model level hierarchy """

    default_behaviour = models.CharField(
        max_length=5, choices=RULE_TYPES, default="Allow"
    )

    def __str__(self):
        return "%s.%s %s" % (self.app, self.model, self.default_behaviour)


class RBACAppModelAction(models.Model):
    """ Valid Actions for an App and Model combination """

    app = models.CharField(max_length=15)
    """ Application level hierarchy """

    model = models.CharField(max_length=15)
    """ model level hierarchy """

    valid_action = models.CharField(max_length=15)
    """ valid actions for this combination """

    description = models.CharField(max_length=100)
    """ description of what this does """


class RBACAdminGroup(models.Model):
    """ Admin Group definitions """

    name_qualifier = models.CharField(max_length=50)
    """ eg "organisations.trumps" """

    name_item = models.CharField(max_length=100)
    """ chosen by the admin. appends onto name_qualifier """

    description = models.TextField()
    """ Free format decription """

    created_date = models.DateTimeField("Create Date", default=timezone.now)
    """ date created """

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, blank=True, null=True
    )
    """ Standard User object """

    class Meta:
        unique_together = ["name_qualifier", "name_item"]

    def __str__(self):
        return "%s.%s - %s" % (self.name_qualifier, self.name_item, self.description)

    @property
    def name(self):
        return "%s.%s" % (self.name_qualifier, self.name_item)


class RBACAdminUserGroup(models.Model):
    """ Maps admins to Groups """

    member = models.ForeignKey(User, on_delete=models.CASCADE)
    """ Standard User object """

    group = models.ForeignKey(RBACAdminGroup, on_delete=models.CASCADE)
    """ RBAC Group """

    def __str__(self):
        return "%s - %s" % (self.group, self.member)


class RBACAdminGroupRole(models.Model):
    """ Admin model to map a group to a role. """

    group = models.ForeignKey(RBACAdminGroup, on_delete=models.CASCADE)
    """ RBACGroup for this Role """

    app = models.CharField(max_length=15)
    """ Application level hierarchy """

    model = models.CharField(max_length=15)
    """ model level hierarchy """

    model_id = models.IntegerField(blank=True, null=True)
    """ Instance of model level hierarchy """

    def __str__(self):
        return "%s - %s" % (self.group, self.role)

    @property
    def role(self):
        """Returns the role in dotted format."""
        if self.model_id:
            return "%s.%s.%s" % (self.app, self.model, self.model_id)
        else:
            return "%s.%s" % (self.app, self.model)


class RBACAdminTree(models.Model):
    """ Control where in the tree a member of a group can create groups """

    group = models.ForeignKey(RBACAdminGroup, on_delete=models.CASCADE)
    """ RBACGroup for this Role """

    tree = models.CharField(max_length=100, unique=True)
    """ tree is an allowed entry point for a user. e.g. rbac.org.org """

    def __str__(self):
        return self.tree
