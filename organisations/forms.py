import datetime

import bleach
from crispy_forms.helper import FormHelper
from django import forms
from django_summernote.widgets import SummernoteInplaceWidget

from accounts.models import User, UnregisteredUser
import accounts.views as accounts_views
from cobalt.settings import (
    ABF_STATES,
    BLEACH_ALLOWED_TAGS,
    BLEACH_ALLOWED_ATTRIBUTES,
    BLEACH_ALLOWED_STYLES,
)
from rbac.core import rbac_user_has_role
from .models import (
    Organisation,
    MembershipType,
    MemberClubEmail,
    MemberMembershipType,
    ClubTag,
)


def membership_type_choices(club):
    """Return membership choices for a club"""

    # Get membership type drop down
    membership_types = MembershipType.objects.filter(organisation=club).values_list(
        "id", "name"
    )
    return [
        (membership_type[0], membership_type[1]) for membership_type in membership_types
    ]


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
            "state": forms.Select(
                choices=choices,
            ),
        }

    def __init__(self, *args, **kwargs):

        # Get user parameter so we can check access in validation
        user = kwargs.pop("user", None)

        # Call Super()
        super().__init__(*args, **kwargs)

        # Add field
        self.user = user

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
            self.add_error("state", "No state body found for this state.")
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
            "is_default",
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
    """Form for adding or editing a local email address for a club unregistered member"""

    email = forms.EmailField(label="Club email address (private)", required=False)


class UserMembershipForm(forms.Form):
    """Form for getting a registered user and a membership type"""

    member = forms.IntegerField()
    membership_type = forms.ChoiceField()
    home_club = forms.BooleanField(initial=True, required=False)

    def __init__(self, *args, **kwargs):
        self.club = kwargs.pop("club")
        super().__init__(*args, **kwargs)
        self.fields["membership_type"].choices = membership_type_choices(self.club)

    def clean_home_club(self):
        """Check that this user doesn't already have a home club"""

        home_club = self.cleaned_data["home_club"]
        member_id = self.cleaned_data["member"]
        member = User.objects.get(pk=member_id)

        if home_club:
            other_club = (
                MemberMembershipType.objects.active()
                .filter(system_number=member.system_number)
                .filter(home_club=True)
                .exclude(membership_type__organisation=self.club)
                .first()
            )
            if other_club:
                self.add_error(
                    "member",
                    f"{member.full_name} already has {other_club.membership_type.organisation} as their home club",
                )

        return home_club


class UnregisteredUserAddForm(forms.Form):
    """Form for adding an unregistered user along with the email, home club and membership type"""

    system_number = forms.IntegerField()
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    mpc_email = forms.EmailField(
        label="Email Address (accessible by all clubs)", required=False
    )
    club_email = forms.EmailField(label="Club email address (private)", required=False)
    membership_type = forms.ChoiceField()
    home_club = forms.BooleanField(initial=True, required=False)

    def __init__(self, *args, **kwargs):
        self.club = kwargs.pop("club")
        super().__init__(*args, **kwargs)
        self.fields["membership_type"].choices = membership_type_choices(self.club)

    def clean_system_number(self):
        system_number = self.cleaned_data["system_number"]

        is_valid, is_member, _ = accounts_views.check_system_number(system_number)

        if not is_valid:
            self.add_error("system_number", "Invalid number")
        if is_member:
            self.add_error(
                "system_number",
                "This user is already registered. You can add them as a member, not an unregistered member",
            )

        return system_number

    def clean_home_club(self):
        """Users can only have one home club"""
        home_club = self.cleaned_data["home_club"]
        system_number = self.cleaned_data["system_number"]

        if (
            home_club
            and MemberMembershipType.objects.active()
            .filter(system_number=system_number)
            .filter(home_club=True)
            .exclude(membership_type__organisation=self.club)
            .exists()
        ):
            self.add_error("home_club", "User already has a home club")
        return home_club


class CSVUploadForm(forms.Form):
    """Form for uploading a CSV to load unregistered members"""

    membership_type = forms.ChoiceField()
    home_club = forms.BooleanField(initial=True, required=False)
    file_type = forms.ChoiceField(
        choices=[
            ("CSV", "Generic CSV"),
            ("CS2", "Compscore"),
            ("Pianola", "Pianola Export"),
        ]
    )

    def __init__(self, *args, **kwargs):
        self.club = kwargs.pop("club")
        super().__init__(*args, **kwargs)
        self.fields["membership_type"].choices = membership_type_choices(self.club)


class MPCForm(forms.Form):
    """Form for uploading a CSV to load unregistered members"""

    membership_type = forms.ChoiceField()

    def __init__(self, *args, **kwargs):
        self.club = kwargs.pop("club")
        super().__init__(*args, **kwargs)
        self.fields["membership_type"].choices = membership_type_choices(self.club)


class TagForm(forms.Form):
    """Form to add a tag to an organisation"""

    tag_name = forms.CharField(
        max_length=50,
        label="",
        widget=forms.TextInput(attrs={"placeholder": "Add new tag"}),
    )

    def __init__(self, *args, **kwargs):
        self.club = kwargs.pop("club")
        super().__init__(*args, **kwargs)

    def clean_tag_name(self):
        tag_name = self.cleaned_data["tag_name"]
        if tag_name.lower() == "everyone":
            self.add_error(
                "tag_name", "No need to add everyone, the system does that for you."
            )

        if ClubTag.objects.filter(organisation=self.club, tag_name=tag_name).exists():
            self.add_error("tag_name", "Duplicate name")
        return tag_name


class TagMultiForm(forms.Form):
    """Form to select multiple tags"""

    tags = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, **kwargs):
        self.club = kwargs.pop("club")
        super().__init__(*args, **kwargs)

        # Get tags for this club
        club_tags = ClubTag.objects.filter(organisation=self.club).values_list(
            "id", "tag_name"
        )

        # Add as choices
        self.fields["tags"].choices = [
            (club_tag[0], club_tag[1]) for club_tag in club_tags
        ]
        self.fields["tags"].choices.insert(0, (0, "Everyone"))

    def clean_tags(self):
        tags = self.cleaned_data["tags"]
        if len(tags) == 0:
            self.add_error("tags", "You must select at least one tag")

        return tags


class UnregisteredUserMembershipForm(forms.Form):
    """Form for handling home club and membership type"""

    membership_type = forms.ChoiceField()
    home_club = forms.BooleanField(initial=True, required=False)

    def __init__(self, *args, **kwargs):
        self.club = kwargs.pop("club")
        self.system_number = kwargs.pop("system_number")
        super().__init__(*args, **kwargs)
        self.fields["membership_type"].choices = membership_type_choices(self.club)

    def clean_home_club(self):
        """Users can only have one home club"""
        home_club = self.cleaned_data["home_club"]

        if (
            home_club
            and MemberMembershipType.objects.active()
            .filter(system_number=self.system_number)
            .filter(home_club=True)
            .exclude(membership_type__organisation=self.club)
            .exists()
        ):
            self.add_error("home_club", "User already has a home club")
        return home_club
