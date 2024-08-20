import datetime

import bleach
from crispy_forms.helper import FormHelper
from django import forms
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


def membership_type_choices(club):
    """Return membership choices for a club"""

    # Get membership type drop down
    membership_types = MembershipType.objects.filter(organisation=club).values_list(
        "id", "name"
    )
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
            "full_club_admin",
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

        # JPG CLEAN UP
        # try:
        #     datetime.datetime(
        #         year=1967,
        #         month=cleaned_data["membership_part_year_date_month"],
        #         day=cleaned_data["membership_part_year_date_day"],
        #     )
        # except ValueError:
        #     self.add_error("membership_part_year_date_month", "Invalid date")
        #     return

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
            "mobile",
            "other_phone",
            "dob",
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
    payment_method = forms.ChoiceField(label="Payment method", required=True)
    # JPG clean up
    # is_paid = forms.BooleanField(label="Mark as paid", required=False)

    def __init__(self, *args, **kwargs):
        self.club = kwargs.pop("club")
        registered = kwargs.pop("registered")
        super(MembershipExtendForm, self).__init__(*args, **kwargs)
        self.fields["payment_method"].choices = membership_payment_method_choices(
            self.club, registered
        )


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
        self.club = kwargs.pop("club")
        registered = kwargs.pop("registered")
        super(MembershipRawEditForm, self).__init__(*args, **kwargs)
        self.fields["membership_type"].choices = membership_type_choices(self.club)
        self.fields["payment_method"].choices = membership_payment_method_choices(
            self.club, registered
        )


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
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
    )
    end_date = forms.DateField(
        label="End date",
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
    )
    fee = forms.DecimalField(label="Fee", max_digits=10, decimal_places=2)
    due_date = forms.DateField(
        label="Payment due date",
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
    )
    # JPG clean up
    # is_paid = forms.BooleanField(label="Mark as paid", required=False)
    payment_method = forms.ChoiceField(label="Payment method", required=True)

    send_welcome_pack = forms.BooleanField(initial=True, required=False)

    def __init__(self, *args, **kwargs):
        self.club = kwargs.pop("club")
        registered = kwargs.pop("registered")
        super(MembershipChangeTypeForm, self).__init__(*args, **kwargs)
        self.fields["membership_type"].choices = membership_type_choices(self.club)
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
        if start_date > today:
            raise forms.ValidationError("Start date cannot be in the future")
        return start_date

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
