import datetime

from crispy_forms.helper import FormHelper
from django import forms

from cobalt.settings import ABF_STATES
from rbac.core import rbac_user_has_role
from .models import Organisation, MembershipType, MemberClubEmail


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
            "secretary",
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

        # Make State a choice field
        choices = [("", "Select State...")]
        for state in ABF_STATES:
            choices.append((ABF_STATES[state][1], ABF_STATES[state][1]))
        widgets = {
            # Need position relative or crispy forms makes a mess of the drop down
            "state": forms.Select(
                choices=choices,
            ),
        }

    def __init__(self, *args, **kwargs):

        # Get user parameter so we can check access in validation
        user = kwargs.pop("user", None)

        # Call Super()
        super(OrgForm, self).__init__(*args, **kwargs)

        # Add field
        self.user = user

        # Remove label from dropdown
        self.fields["state"].label = False

    def clean_state(self):
        """check this user has access to this state"""

        from .views.general import get_rbac_model_for_state

        state = self.cleaned_data["state"]

        # See if this has changed
        if "state" not in self.changed_data:
            return state

        if not state:
            self.add_error("state", "State cannot be empty")
            return state

        # Get model id for this state
        rbac_model_for_state = get_rbac_model_for_state(state)

        if not rbac_model_for_state:
            self.add_error("state", "No RBAC model found for this state.")
            return state

        # Check access - state or admin both work
        if not (
            rbac_user_has_role(self.user, "orgs.state.%s.edit" % rbac_model_for_state)
            or rbac_user_has_role(self.user, "orgs.admin.edit")
        ):
            self.add_error(
                "state",
                "You do not have permissions to create or edit a club in this state.",
            )

        return state


class MembershipTypeForm(forms.ModelForm):
    class Meta:
        model = MembershipType
        fields = (
            "name",
            "description",
            "annual_fee",
            "part_year_fee",
            "does_not_pay_session_fees",
            "does_not_renew",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # {{ form | crispy }} stuffs up checkboxes and {% crispy form %} adds </form>. This prevents this.
        self.helper = FormHelper(self)
        self.helper.form_tag = False


class OrgDatesForm(forms.ModelForm):
    class Meta:
        model = Organisation
        fields = (
            "membership_renewal_date_day",
            "membership_renewal_date_month",
            "membership_part_year_date_day",
            "membership_part_year_date_month",
        )

    def clean(self):
        """custom validation"""
        cleaned_data = super(OrgDatesForm, self).clean()

        # Test for a valid month and day (Feb 29th will always fail)
        try:
            datetime.datetime(
                year=1967,
                month=cleaned_data["membership_renewal_date_month"],
                day=cleaned_data["membership_renewal_date_day"],
            )
        except ValueError:
            self.add_error("membership_renewal_date_month", "Invalid date")
            return

        try:
            datetime.datetime(
                year=1967,
                month=cleaned_data["membership_part_year_date_month"],
                day=cleaned_data["membership_part_year_date_day"],
            )
        except ValueError:
            self.add_error("membership_part_year_date_month", "Invalid date")
            return

        return self.cleaned_data


class MemberClubEmailForm(forms.Form):

    email = forms.EmailField(label="Club email address (private)", required=False)
