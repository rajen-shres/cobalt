from django import forms
from django.core.validators import RegexValidator
from .models import RBACAdminTree, RBACAdminUserGroup, RBACGroup, RBACAdminGroup


class AddGroup(forms.Form):
    """ Add a new group to RBAC """

    name_item = forms.CharField(
        label="Name",
        max_length=50,
        validators=[
            RegexValidator(
                regex=" ",
                message="Spaces are not allowed in the name",
                code="invalid_name_item",
                inverse_match=True,
            ),
        ],
    )
    description = forms.CharField(label="Description", max_length=50)
    add_self = forms.BooleanField(label="Add Yourself", required=False)

    # We need the logged in user to get the RBACTreeUser values, add a parameter to init
    # This is so we can build the drop down list dynamically
    # The drop down list also needs any exising sub parts of the tree.
    # e.g. if a user has access to a.b.c then also show a.b.c.d if it already exists in tree
    def __init__(self, *args, **kwargs):
        # get user
        self.user = kwargs.pop("user", None)

        # get admin or normal
        self.environment = kwargs.pop("environment", None)

        # create form
        super(AddGroup, self).__init__(*args, **kwargs)

        # build name_qualifier list for this user
        choices = []

        # get their admin groups
        group_list = RBACAdminUserGroup.objects.filter(member=self.user).values_list(
            "group"
        )

        # admintree is shared so filter out the parts we want
        queryset = (
            RBACAdminTree.objects.filter(group__in=group_list)
            .order_by("tree")
            .distinct("tree")
            .values_list("tree")
        )
        if self.environment == "admin":
            queryset = queryset.filter(tree__startswith="admin.")
        else:
            queryset = queryset.exclude(tree__startswith="admin.")

        # load whole tree - where things are
        whole_tree_qs = (
            RBACGroup.objects.all()
            .distinct("name_qualifier", "name_item")
            .values_list("name_qualifier")
        )
        whole_tree = []
        for query in whole_tree_qs:
            whole_tree.append(query[0])

        # load whole admin tree - where things could be
        whole_tree_qs = RBACAdminTree.objects.all().distinct("tree").values_list("tree")
        for query in whole_tree_qs:
            if query[0] not in whole_tree:
                whole_tree.append(query[0])

        whole_tree.sort()

        already_included = []
        for item in queryset:
            # add item and any existing lower parts of tree to choices
            item = "%s" % item
            for wtree in whole_tree:
                if wtree.find(item) == 0 and wtree not in already_included:
                    choices.append((wtree, wtree))
                    already_included.append(wtree)

        self.fields["name_qualifier"] = forms.ChoiceField(
            label="Qualifier", choices=choices, required=False
        )

    def clean(self):
        """ We allow uses to put . into the name_item so here we split that
            out and put the part before the . into name_qualifier
            but only on group creation. """
        super().clean()

        if not self.is_valid():
            return self.cleaned_data

        qualifier = self.cleaned_data["name_qualifier"]
        item = self.cleaned_data["name_item"]

        if qualifier == "" and "." in item:  # Update - no full stops
            self._errors["name_item"] = self.error_class(
                ["Full stops not permitted in name when editing group."]
            )

        else:

            string = "%s.%s" % (qualifier, item)
            parts = string.split(".")
            qualifier = ".".join(parts[:-1])
            item = parts[-1]

            # check for dupicates - this form is used by two models so load the right one
            if self.environment == "admin":
                dupe = RBACAdminGroup.objects.filter(
                    name_qualifier=qualifier, name_item=item,
                ).exists()
            else:
                dupe = RBACGroup.objects.filter(
                    name_qualifier=qualifier, name_item=item,
                ).exists()
            if dupe:
                msg = "%s.%s already taken" % (qualifier, item)
                self._errors["name_item"] = self.error_class([msg])

        self.cleaned_data["name_qualifier"] = qualifier
        self.cleaned_data["name_item"] = item

        return self.cleaned_data
