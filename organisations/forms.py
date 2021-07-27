from django import forms

from rbac.core import rbac_user_has_role
from .models import Organisation


# TODO: Replace when club admin work complete
class OrgFormOld(forms.ModelForm):
    class Meta:
        model = Organisation
        fields = (
            "name",
            "address1",
            "address2",
            "suburb",
            "state",
            "postcode",
            "bank_bsb",
            "bank_account",
        )


class OrgForm(forms.ModelForm):
    class Meta:
        model = Organisation
        fields = (
            "name",
            "org_id",
            "club_email",
            "club_website",
            "address1",
            "address2",
            "suburb",
            "state",
            "postcode",
            "bank_bsb",
            "bank_account",
        )

    def __init__(self, *args, **kwargs):

        # Get user parameter so we can check access
        user = kwargs.pop("user", None)

        # Call Super()
        super(OrgForm, self).__init__(*args, **kwargs)

        # Add field
        self.user = user

    def clean_state(self):
        """check this user has access to this state"""

        from .views import get_rbac_model_for_state

        state = self.cleaned_data["state"]
        if not state:
            self.add_error("state", "State cannot be empty")

        # Get model id for this state
        rbac_model_for_state = get_rbac_model_for_state(state)

        # Check access
        if not (
            rbac_user_has_role(self.user, "orgs.org.%s.edit" % rbac_model_for_state)
            or rbac_user_has_role(self.user, "orgs.admin.edit")
        ):
            self.add_error(
                "state", "You do not have permissions to create a club in this state."
            )

        return state
