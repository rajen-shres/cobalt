import datetime

import bleach
from crispy_forms.helper import FormHelper
from django import forms
from django.core.validators import MinValueValidator
from django.forms import formset_factory
from django_summernote.widgets import SummernoteInplaceWidget
from django.utils import timezone
from PIL import Image

#  Moved to avoid circular reference issue on imports
# import accounts.views.admin
from accounts.utils import check_system_number

from cobalt.settings import (
    ABF_STATES,
    BLEACH_ALLOWED_TAGS,
    BLEACH_ALLOWED_ATTRIBUTES,
    BLEACH_ALLOWED_STYLES,
)
from notifications.models import EmailAttachment
from payments.models import OrgPaymentMethod
from rbac.core import rbac_user_has_role
from results.models import ResultsFile
from .models import (
    Organisation,
    MembershipType,
    MemberMembershipType,
    ClubTag,
    OrganisationFrontPage,
    OrgVenue,
    OrgEmailTemplate,
    WelcomePack,
    MemberClubDetails,
)


def membership_type_choices(club, exclude_id=None):
    """Return membership choices for a club"""

    # Get membership type drop down
    membership_type_qs = MembershipType.objects.filter(organisation=club)

    if exclude_id:
        membership_type_qs = membership_type_qs.exclude(
            id=exclude_id,
        )

    membership_types = membership_type_qs.values_list("id", "name")

    return [
        (membership_type[0], membership_type[1]) for membership_type in membership_types
    ]


def membership_payment_method_choices(club, registered, allow_none=True):
    """Return membership payment method choices for a club

    Adds a null choice with value -1, and removes IOU as a valid choice
    Removes bridge credits if not registered.
    """

    all_methods = OrgPaymentMethod.objects.filter(
        organisation=club,
        active=True,
    ).values_list("id", "payment_method")

    method_choices = [(-1, "-")] if allow_none else []

    for id, desc in all_methods:
        if desc != "IOU" and not (desc == "Bridge Credits" and not registered):
            method_choices.append((id, desc))

    return method_choices


def club_email_template_choices(club):
    """Return available club email template choices

    Returns a list of (OrgEmailTemplate id, template name)
    including a null choice of (-1. '-')
    """

    choices = list(
        OrgEmailTemplate.objects.filter(organisation=club).values_list(
            "id", "template_name"
        )
    )
    return [(-1, "-")] + choices


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
            "default_secondary_payment_method",
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

        # Handle default_Secondary_payment_methods
        instance = kwargs.get("instance")
        if instance:
            # Org already exists so we can show choices
            org_payment_types = (
                OrgPaymentMethod.objects.filter(organisation=instance, active=True)
                .exclude(payment_method="Bridge Credits")
                .values_list("id", "payment_method")
            )
            self.fields["default_secondary_payment_method"].choices = org_payment_types
            if instance.default_secondary_payment_method:
                self.fields[
                    "default_secondary_payment_method"
                ].initial = instance.default_secondary_payment_method.id
        else:
            # New org - remove option
            self.fields.pop("default_secondary_payment_method")

    def clean_state(self):
        """check this user has access to this state"""

        from .views.general import get_rbac_model_for_state

        state = self.cleaned_data["state"]

        if not state:
            self.add_error("state", "State cannot be empty")
            return state

        # See if this has changed
        if "state" not in self.changed_data:
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
            "is_default",
            "grace_period_days",
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
            "full_club_admin",
        )

    def clean_membership_renewal_date_month(self):
        month = self.cleaned_data.get("membership_renewal_date_month")

        if month is None:
            raise forms.ValidationError("This field is required.")
        if not 1 <= month <= 12:
            raise forms.ValidationError("Month must be between 1 and 12.")

        return month

    def clean_membership_renewal_date_day(self):
        day = self.cleaned_data.get("membership_renewal_date_day")

        if day is None:
            raise forms.ValidationError("This field is required.")
        if not 1 <= day <= 31:
            raise forms.ValidationError("Day must be between 1 and 31.")

        return day

    def clean(self):
        """custom validation"""
        cleaned_data = super(OrgDatesForm, self).clean()

        month = cleaned_data.get("membership_renewal_date_month")
        day = cleaned_data.get("membership_renewal_date_day")

        # Only validate the date if both day and month have passed individual validation
        if month and day:
            try:
                datetime.datetime(year=1967, month=month, day=day)
            except ValueError:
                self.add_error("membership_renewal_date_month", "Invalid date")
                self.add_error("membership_renewal_date_day", "Invalid date")

        return self.cleaned_data


class MemberClubEmailForm(forms.Form):
    """Form for adding or editing a local email address for a club unregistered member"""

    email = forms.EmailField(
        label="Email address (accessible by this club only)", required=False
    )


class MemberClubDetailsForm(forms.ModelForm):
    """Form for editing club member details"""

    class Meta:
        model = MemberClubDetails
        fields = (
            "email",
            "address1",
            "address2",
            "state",
            "postcode",
            "preferred_phone",
            "other_phone",
            "dob",
            "joined_date",
            "left_date",
            "club_membership_number",
            "emergency_contact",
            "notes",
        )


class MembershipExtendForm(forms.Form):
    """Form for extending an existing membership"""

    new_end_date = forms.DateField(
        label="New end date",
        widget=forms.DateInput(attrs={"type": "date"}),
        required=True,
    )
    fee = forms.DecimalField(label="Fee", max_digits=10, decimal_places=2)
    due_date = forms.DateField(
        label="Payment due date",
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
    )
    auto_pay_date = forms.DateField(
        label="Auto payment date",
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
    )
    payment_method = forms.ChoiceField(label="Payment method", required=True)
    send_notice = forms.BooleanField(
        label="Send a renewal notice",
        required=False,
    )
    club_template = forms.ChoiceField(label="Club email template", required=True)
    email_subject = forms.CharField(label="Subject", required=False)
    email_content = forms.CharField(
        label="Renewal message",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "cols": 40}),
    )

    def __init__(self, *args, **kwargs):
        self.club = kwargs.pop("club")
        registered = kwargs.pop("registered")
        super(MembershipExtendForm, self).__init__(*args, **kwargs)
        self.fields["payment_method"].choices = membership_payment_method_choices(
            self.club, registered
        )
        self.fields["club_template"].choices = club_email_template_choices(self.club)

    def clean_fee(self):
        fee = self.cleaned_data.get("fee")
        if fee is not None and fee < 0:
            self.add_error("fee", "Fee cannot be negative.")
        return fee


class MembershipPaymentForm(forms.Form):
    """Form for paying membership fees. Does not provide a no selection option for the payment method"""

    payment_method = forms.ChoiceField(label="Payment method", required=True)

    def __init__(self, *args, **kwargs):
        self.club = kwargs.pop("club")
        registered = kwargs.pop("registered")
        super(MembershipPaymentForm, self).__init__(*args, **kwargs)
        self.fields["payment_method"].choices = membership_payment_method_choices(
            self.club, registered, allow_none=False
        )


class MembershipRawEditForm(forms.ModelForm):
    """Form for raw editing of a membership record"""

    membership_type = forms.ChoiceField(label="Membership Type", required=True)

    payment_method = forms.ChoiceField(label="Payment method", required=True)

    membership_state = forms.ChoiceField(
        label="Membership State",
        choices=MemberMembershipType.MEMBERSHIP_STATE,
        required=True,
    )

    class Meta:
        model = MemberMembershipType
        exclude = [
            "system_number",
            "home_club",
            "last_modified_by",
            "membership_type",
            "payment_method",
            "membership_state",
        ]

    def __init__(self, *args, **kwargs):
        if "full_club_admin" in kwargs:
            self.full_club_admin = kwargs.pop("full_club_admin")
        else:
            self.full_club_admin = True
        self.club = kwargs.pop("club")
        registered = kwargs.pop("registered")
        super(MembershipRawEditForm, self).__init__(*args, **kwargs)
        self.fields["membership_type"].choices = membership_type_choices(self.club)
        self.fields["payment_method"].choices = membership_payment_method_choices(
            self.club, registered
        )

        # handle initialisation of excluded fields
        # Set initial values manually if an instance is provided
        if self.instance and self.instance.pk:
            self.fields["membership_type"].initial = (
                self.instance.membership_type.id
                if self.instance.membership_type
                else None
            )
            self.fields["payment_method"].initial = (
                self.instance.payment_method.id
                if self.instance.payment_method
                else None
            )
            self.fields["membership_state"].initial = self.instance.membership_state

        # Alternatively, if initial values were passed in the form initialization
        if "initial" in kwargs:
            self.fields["membership_type"].initial = kwargs["initial"].get(
                "membership_type", self.fields["membership_type"].initial
            )
            self.fields["payment_method"].initial = kwargs["initial"].get(
                "payment_method", self.fields["payment_method"].initial
            )
            self.fields["membership_state"].initial = kwargs["initial"].get(
                "membership_state", self.fields["membership_state"].initial
            )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")

        if self.full_club_admin:
            if not start_date:
                self.add_error("start_date", "Start date is required")

        return cleaned_data

    def clean_fee(self):
        fee = self.cleaned_data.get("fee")
        if fee is not None and fee < 0:
            self.add_error("fee", "Fee cannot be negative.")
        return fee

    def save(self, commit=True):
        instance = super(MembershipRawEditForm, self).save(commit=False)
        # Update the instance with the form's cleaned data
        instance.membership_state = self.cleaned_data.get("membership_state")
        if self.cleaned_data.get("membership_type") == -1:
            new_membership_type = None
        else:
            try:
                new_membership_type = MembershipType.objects.get(
                    pk=self.cleaned_data.get("membership_type")
                )
            except MembershipType.DoesNotExist:
                new_membership_type = None
        instance.membership_type = new_membership_type

        if self.cleaned_data.get("payment_method") == -1:
            new_payment_method = None
        else:
            try:
                new_payment_method = OrgPaymentMethod.objects.get(
                    pk=self.cleaned_data.get("payment_method")
                )
            except OrgPaymentMethod.DoesNotExist:
                new_payment_method = None
        instance.payment_method = new_payment_method

        if commit:
            instance.save()
        return instance


class MembershipChangeTypeForm(forms.Form):
    """Form for changing or creating a new membership
    Membership type options are derived from the club parameter"""

    new_system_number = forms.IntegerField(
        label="System Number",
        required=False,
    )
    new_email = forms.EmailField(
        label="Email Address (accessible by this club only)", required=False
    )
    membership_type = forms.ChoiceField(label="Membership Type", required=True)
    start_date = forms.DateField(
        label="Start date",
        # widget=forms.DateInput(attrs={"type": "date"}),
        required=True,
    )
    end_date = forms.DateField(
        label="End date",
        # widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
    )
    fee = forms.DecimalField(
        label="Fee",
        max_digits=10,
        decimal_places=2,
    )
    due_date = forms.DateField(
        label="Payment due date",
        # widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
    )
    # JPG clean up
    # is_paid = forms.BooleanField(label="Mark as paid", required=False)
    payment_method = forms.ChoiceField(label="Payment method", required=False)

    send_welcome_pack = forms.BooleanField(initial=True, required=False)

    def __init__(self, *args, **kwargs):
        """Form initialiser
        Note: must have club and registered arguements. Can optionally have
        exclude_id.
        """
        self.club = kwargs.pop("club")
        registered = kwargs.pop("registered")
        if "exclude_id" in kwargs:
            exclude_id = kwargs.pop("exclude_id")
        else:
            exclude_id = None
        super(MembershipChangeTypeForm, self).__init__(*args, **kwargs)
        self.fields["membership_type"].choices = membership_type_choices(
            self.club, exclude_id=exclude_id
        )
        self.fields["payment_method"].choices = membership_payment_method_choices(
            self.club, registered
        )

        # JPG clean up
        # If this club doesn't have a membership pack then don't show on form
        # if not WelcomePack.objects.filter(organisation=self.club).exists():
        #     del self.fields["send_welcome_email"]

    def clean_start_date(self):
        start_date = self.cleaned_data.get("start_date")
        today = timezone.now().date()
        if start_date > today + datetime.timedelta(days=1):
            # Allow a start date of tomorrow to allow ending currnt today
            self.add_error("start_date", "Start date cannot be in the future")
        return start_date

    def clean_fee(self):
        fee = self.cleaned_data.get("fee")
        if fee is not None and fee < 0:
            self.add_error("fee", "Fee cannot be negative.")
        return fee

    def clean(self):
        cleaned_data = super().clean()
        start_date = self.cleaned_data.get("start_date")
        end_date = self.cleaned_data.get("end_date")
        if start_date and end_date and start_date > end_date:
            raise forms.ValidationError("End date must be after the start date")
        return cleaned_data


class UserMembershipForm(forms.Form):
    """Form for getting a registered user and a membership type"""

    system_number = forms.IntegerField()
    membership_type = forms.ChoiceField()
    home_club = forms.BooleanField(initial=False, required=False)
    send_welcome_email = forms.BooleanField(initial=True, required=False)

    def __init__(self, *args, **kwargs):
        self.club = kwargs.pop("club")
        super().__init__(*args, **kwargs)
        self.fields["membership_type"].choices = membership_type_choices(self.club)

        # If this club doesn't have a membership pack then don't show on form
        if not WelcomePack.objects.filter(organisation=self.club).exists():
            del self.fields["send_welcome_email"]

    # def clean_home_club(self):
    #     """Check that this user doesn't already have a home club"""
    #
    #     home_club = self.cleaned_data["home_club"]
    #     member_id = self.cleaned_data["member"]
    #     member = User.objects.get(pk=member_id)
    #
    #     if home_club:
    #         other_club = (
    #             MemberMembershipType.objects.active()
    #             .filter(system_number=member.system_number)
    #             .filter(home_club=True)
    #             .exclude(membership_type__organisation=self.club)
    #             .first()
    #         )
    #         if other_club:
    #             self.add_error(
    #                 "member",
    #                 f"{member.full_name} already has {other_club.membership_type.organisation} as their home club",
    #             )
    #
    #     return home_club


class UnregisteredUserAddForm(forms.Form):
    """Form for adding an unregistered user along with the email, home club and membership type"""

    system_number = forms.IntegerField()
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    club_email = forms.EmailField(
        label="Email Address (accessible by this club only)", required=False
    )
    membership_type = forms.ChoiceField()
    home_club = forms.BooleanField(initial=True, required=False)
    send_welcome_email = forms.BooleanField(initial=True, required=False)

    def __init__(self, *args, **kwargs):
        self.club = kwargs.pop("club")
        super().__init__(*args, **kwargs)
        self.fields["membership_type"].choices = membership_type_choices(self.club)

        # If this club doesn't have a membership pack then don't show on form
        if not WelcomePack.objects.filter(organisation=self.club).exists():
            del self.fields["send_welcome_email"]

    def clean_system_number(self):
        system_number = self.cleaned_data["system_number"]

        is_valid, is_member, _ = check_system_number(system_number)

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
            and MemberMembershipType.objects.filter(system_number=system_number)
            .filter(home_club=True)
            .exclude(membership_type__organisation=self.club)
            .exists()
        ):
            self.add_error("home_club", "User already has a home club")
        return home_club


class ContactAddForm(forms.Form):
    """Form for adding a contact"""

    first_name = forms.CharField(max_length=150, initial="", required=True)
    last_name = forms.CharField(max_length=150, initial="", required=True)


class CSVUploadForm(forms.Form):
    """Form for uploading a CSV to load unregistered members"""

    membership_type = forms.ChoiceField()
    home_club = forms.BooleanField(initial=True, required=False)
    overwrite = forms.BooleanField(initial=False, required=False)
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


class CSVContactUploadForm(forms.Form):
    """Form for uploading a CSV to load contacts"""

    file_type = forms.ChoiceField(
        choices=[
            ("CSV", "Generic CSV"),
            ("CS2", "Compscore"),
            ("Pianola", "Pianola Export"),
        ]
    )


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

    selected_tags = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, **kwargs):
        self.club = kwargs.pop("club")
        super().__init__(*args, **kwargs)

        # Get tags for this club
        club_tags = (
            ClubTag.objects.filter(organisation=self.club)
            .order_by("tag_name")
            .values_list("id", "tag_name")
        )

        # Add as choices
        self.fields["selected_tags"].choices = [
            (club_tag[0], club_tag[1]) for club_tag in club_tags
        ]
        self.fields["selected_tags"].choices.insert(0, ("0", "EVERYONE"))

    def clean_tags(self):
        tags = self.cleaned_data["selected_tags"]
        if len(tags) == 0:
            self.add_error("tags", "You must select at least one tag")

        return tags


class TemplateForm(forms.ModelForm):
    """Form for editing email template"""

    class Meta:
        model = OrgEmailTemplate
        fields = (
            "footer",
            "template_name",
            "from_name",
            "reply_to",
            "box_colour",
            "box_font_colour",
        )

    footer = forms.CharField(
        # This shouldn't be needed but is
        required=False,
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "height": "250",
                    "codemirror": {"theme": "monokai"},
                    "placeholder": "<br><br>(Optional) Enter your footer here. This will appear at the bottom of your email.",
                }
            }
        ),
    )
    reply_to = forms.EmailField(required=False)


class TemplateBannerForm(forms.ModelForm):
    """Form for editing email template banner"""

    x = forms.FloatField(widget=forms.HiddenInput())
    y = forms.FloatField(widget=forms.HiddenInput())
    width = forms.FloatField(widget=forms.HiddenInput())
    height = forms.FloatField(widget=forms.HiddenInput())

    class Meta:

        model = OrgEmailTemplate
        fields = (
            "banner",
            "x",
            "y",
            "width",
            "height",
        )
        widgets = {"file": forms.FileInput(attrs={"accept": "image/*"})}

    def save(self):
        email_template = super(TemplateBannerForm, self).save()

        x = self.cleaned_data.get("x")
        y = self.cleaned_data.get("y")
        w = self.cleaned_data.get("width")
        h = self.cleaned_data.get("height")

        image = Image.open(email_template.banner)

        if image.mode != "RGB":
            image = image.convert("RGB")

        cropped_image = image.crop((x, y, w + x, h + y))
        resized_image = cropped_image.resize((500, 200), Image.ANTIALIAS)
        resized_image.save(email_template.banner.path)

        return email_template


# JPG TO DO Deprecated - moved to notifications
class EmailAttachmentForm(forms.ModelForm):
    """Form for uploading an attachment for a club"""

    class Meta:

        model = EmailAttachment
        fields = ("attachment",)
        widgets = {"attachment": forms.FileInput(attrs={"accept": "*/*"})}


class ResultsFileForm(forms.ModelForm):
    """Form for uploading a results file"""

    class Meta:

        model = ResultsFile
        fields = ("results_file",)
        widgets = {"results_file": forms.FileInput(attrs={"accept": "*/*.xml"})}


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
            and MemberMembershipType.objects.filter(system_number=self.system_number)
            .filter(home_club=True)
            .exclude(membership_type__organisation=self.club)
            .exists()
        ):
            self.add_error("home_club", "User already has a home club")
        return home_club


class FrontPageForm(forms.ModelForm):
    """Form for the front page info for a club"""

    summary = forms.CharField(
        widget=SummernoteInplaceWidget(
            attrs={"summernote": {"placeholder": "<br><br>Build your page here..."}}
        )
    )

    class Meta:
        model = OrganisationFrontPage
        fields = (
            "summary",
            "organisation",
        )

    # def clean_summary(self):
    #     summary = self.cleaned_data["summary"]
    #
    #     summary = bleach.clean(
    #         summary,
    #         strip=True,
    #         tags=BLEACH_ALLOWED_TAGS,
    #         attributes=BLEACH_ALLOWED_ATTRIBUTES,
    #         styles=BLEACH_ALLOWED_STYLES,
    #     )
    #
    #     summary = summary.replace("<", "\n<")
    #
    #     return summary


class VenueForm(forms.Form):
    """Form to add a venue to an organisation"""

    venue_name = forms.CharField(
        max_length=15,
        label="",
        widget=forms.TextInput(attrs={"placeholder": "Add new venue"}),
    )

    def __init__(self, *args, **kwargs):
        self.club = kwargs.pop("club")
        super().__init__(*args, **kwargs)

    def clean_venue_name(self):
        venue_name = self.cleaned_data["venue_name"]

        if OrgVenue.objects.filter(organisation=self.club, venue=venue_name).exists():
            self.add_error("venue_name", "Duplicate name")
        return venue_name


class OrgDefaultSecondaryPaymentMethod(forms.ModelForm):
    class Meta:
        model = Organisation
        fields = ("default_secondary_payment_method",)

    def __init__(self, *args, **kwargs):
        self.club = kwargs.pop("club")
        super().__init__(*args, **kwargs)

        # Get payment methods for this club (excluding Bridge Credits)
        payment_methods = OrgPaymentMethod.objects.filter(
            organisation=self.club, active=True
        ).exclude(payment_method="Bridge Credits")
        our_payment_methods = [
            (payment_method.id, payment_method.payment_method)
            for payment_method in payment_methods
        ]

        self.fields["default_secondary_payment_method"].choices = our_payment_methods
        # Default value if set, or add Select... if not set
        if self.club.default_secondary_payment_method:
            self.fields[
                "default_secondary_payment_method"
            ].initial = self.club.default_secondary_payment_method.id
        else:
            self.fields["default_secondary_payment_method"].choices.insert(
                0, (-1, "Select...")
            )


class PaymentTypeForm(forms.Form):
    """Form to add a payment type to an organisation"""

    payment_name = forms.CharField(
        max_length=15,
        label="",
        widget=forms.TextInput(attrs={"placeholder": "Add new method"}),
    )

    def __init__(self, *args, **kwargs):
        self.club = kwargs.pop("club")
        super().__init__(*args, **kwargs)

    def clean_payment_name(self):
        payment_name = self.cleaned_data["payment_name"]

        if OrgPaymentMethod.objects.filter(
            organisation=self.club, payment_method=payment_name
        ).exists():
            self.add_error("payment_name", "Duplicate name")
        return payment_name


class WelcomePackForm(forms.ModelForm):
    """Form for the welcome packs for a club"""

    welcome_email = forms.CharField(
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "placeholder": "<br><br>Enter your welcome email here..."
                }
            }
        )
    )

    class Meta:
        model = WelcomePack
        fields = (
            "template",
            "welcome_email",
        )

    def __init__(self, *args, **kwargs):
        self.club = kwargs.pop("club")
        super().__init__(*args, **kwargs)

        templates = OrgEmailTemplate.objects.filter(organisation=self.club)
        our_templates = [
            (template.id, template.template_name) for template in templates
        ]

        self.fields["template"].choices = our_templates


class ResultsEmailMessageForm(forms.ModelForm):
    """Form for the results email message sent to players for a club"""

    class Meta:
        model = Organisation
        fields = ("results_email_message",)

    results_email_message = forms.CharField(
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "height": "250",
                    "placeholder": "<br><br>(Optional) Add a message for your members...",
                }
            }
        )
    )


class MinimumBalanceAfterSettlementForm(forms.ModelForm):
    """form for minimum_balance_after_settlement"""

    class Meta:
        model = Organisation
        fields = ("minimum_balance_after_settlement",)


class BulkRenewalLineForm(forms.Form):
    """Options for bulk renewal of a membership type"""

    selected = forms.BooleanField(
        label="Selected",
        required=False,
    )

    membership_type_id = forms.IntegerField(
        label="Membership type id (hidden)",
    )

    membership_type_name = forms.CharField(
        label="Membership type",
    )

    fee = forms.DecimalField(
        label="Fee",
        max_digits=10,
        decimal_places=2,
        required=False,
    )

    due_date = forms.DateField(
        label="Payment due date",
        # widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
    )

    auto_pay_date = forms.DateField(
        label="Auto pay date",
        # widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
    )

    start_date = forms.DateField(
        label="Start date",
        # widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
    )

    end_date = forms.DateField(
        label="End date",
        # widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
    )

    def clean_fee(self):
        fee = self.cleaned_data.get("fee")
        if fee is not None and fee < 0:
            self.add_error("fee", "Fee cannot be negative.")
        return fee


BulkRenewalFormSet = formset_factory(BulkRenewalLineForm, extra=0)


class BulkRenewalOptionsForm(forms.Form):
    """A form for the common options for a batch"""

    send_notice = forms.BooleanField(label="Send renewal notices", required=False)
    club_template = forms.ChoiceField(label="Club email template", required=True)
    email_subject = forms.CharField(label="Subject", required=False)
    email_content = forms.CharField(
        label="Renewal message",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "cols": 40}),
    )

    def __init__(self, *args, **kwargs):
        self.club = kwargs.pop("club")
        super(BulkRenewalOptionsForm, self).__init__(*args, **kwargs)
        self.fields["club_template"].choices = club_email_template_choices(self.club)
