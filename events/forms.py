from decimal import Decimal

import bleach
from django import forms
from django.core.exceptions import ValidationError
from .models import (
    Congress,
    Event,
    Session,
    EventEntryPlayer,
    EventPlayerDiscount,
    CongressMaster,
    Bulletin,
    CongressDownload,
    PartnershipDesk,
)
from organisations.models import Organisation
from django_summernote.widgets import SummernoteInplaceWidget
from cobalt.settings import (
    GLOBAL_ORG,
    GLOBAL_CURRENCY_NAME,
    BRIDGE_CREDITS,
    BLEACH_ALLOWED_TAGS,
    BLEACH_ALLOWED_ATTRIBUTES,
    BLEACH_ALLOWED_STYLES,
)


class CongressForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):

        # Get allowed congress masters as parameter
        congress_masters = kwargs.pop("congress_masters", [])
        super().__init__(*args, **kwargs)

        # Modify congress master if passed
        self.fields["congress_master"].queryset = CongressMaster.objects.filter(
            pk__in=congress_masters
        ).order_by("name")

        # Hide the crispy labels
        self.fields["name"].label = False
        self.fields["year"].label = False
        self.fields["start_date"].label = False
        self.fields["end_date"].label = False
        self.fields["date_string"].label = False
        self.fields["people"].label = False
        self.fields["general_info"].label = False
        self.fields["links"].label = False
        self.fields["venue_name"].label = False
        self.fields["venue_location"].label = False
        self.fields["venue_transport"].label = False
        self.fields["venue_catering"].label = False
        self.fields["venue_additional_info"].label = False
        self.fields["additional_info"].label = False
        self.fields["sponsors"].label = False
        self.fields["payment_method_system_dollars"].label = False
        self.fields["payment_method_bank_transfer"].label = False
        self.fields["payment_method_cash"].label = False
        self.fields["payment_method_cheques"].label = False
        self.fields["payment_method_off_system_pp"].label = False
        self.fields["entry_open_date"].label = False
        self.fields["entry_close_date"].label = False
        self.fields["allow_partnership_desk"].label = False
        self.fields["allow_early_payment_discount"].label = False
        self.fields["early_payment_discount_date"].label = False
        self.fields["allow_youth_payment_discount"].label = False
        self.fields["youth_payment_discount_date"].label = False
        self.fields["youth_payment_discount_age"].label = False
        self.fields["senior_date"].label = False
        self.fields["senior_age"].label = False
        self.fields["bank_transfer_details"].label = False
        self.fields["cheque_details"].label = False
        self.fields["automatic_refund_cutoff"].label = False
        self.fields["congress_type"].label = False
        self.fields["contact_email"].label = False
        self.fields["congress_venue_type"].label = False
        self.fields["online_platform"].label = False
        self.fields["congress_master"].label = False
        # self.fields["automatically_mark_club_pp_as_paid"].label = False

        # mark fields as optional
        self.fields["name"].required = False
        self.fields["year"].required = False
        self.fields["start_date"].required = False
        self.fields["end_date"].required = False
        self.fields["date_string"].required = False
        self.fields["people"].required = False
        self.fields["sponsors"].required = False
        self.fields["general_info"].required = False
        self.fields["links"].required = False
        self.fields["venue_name"].required = False
        self.fields["venue_location"].required = False
        self.fields["venue_transport"].required = False
        self.fields["venue_catering"].required = False
        self.fields["venue_additional_info"].required = False
        self.fields["additional_info"].required = False
        self.fields["payment_method_system_dollars"].required = False
        self.fields["payment_method_bank_transfer"].required = False
        self.fields["payment_method_cash"].required = False
        self.fields["payment_method_cheques"].required = False
        self.fields["payment_method_off_system_pp"].required = False
        self.fields["entry_open_date"].required = False
        self.fields["entry_close_date"].required = False
        self.fields["allow_partnership_desk"].required = False
        self.fields["allow_early_payment_discount"].required = False
        self.fields["early_payment_discount_date"].required = False
        self.fields["allow_youth_payment_discount"].required = False
        self.fields["youth_payment_discount_date"].required = False
        self.fields["youth_payment_discount_age"].required = False
        self.fields["senior_date"].required = False
        self.fields["senior_age"].required = False
        self.fields["bank_transfer_details"].required = False
        self.fields["cheque_details"].required = False
        self.fields["automatic_refund_cutoff"].required = False
        self.fields["contact_email"].required = False
        self.fields["congress_venue_type"].required = False
        self.fields["online_platform"].required = False
        self.fields["congress_master"].required = False
        # self.fields["automatically_mark_club_pp_as_paid"].required = False

    general_info = forms.CharField(
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "height": "250",
                    "placeholder": "<br><br>Enter basic information about the congress.",
                }
            }
        )
    )

    links = forms.CharField(
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "height": "250",
                    "placeholder": "<br><br>Enter links to useful information. This looks good as a list.",
                }
            }
        )
    )

    sponsors = forms.CharField(
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "height": "250",
                    "placeholder": "<br><br>(Optional) Enter information about sponsors and upload pictures and logos.",
                }
            }
        )
    )

    people = forms.CharField(
        widget=SummernoteInplaceWidget(attrs={"summernote": {"height": "250"}})
    )
    venue_transport = forms.CharField(
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "height": "250",
                    "placeholder": "<br><br>Enter information about how to get to the venue, such as public transport or parking.",
                }
            }
        )
    )
    venue_catering = forms.CharField(
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "height": "250",
                    "placeholder": "<br><br>Enter any information about catering that could be useful for attendees.",
                }
            }
        )
    )
    venue_additional_info = forms.CharField(
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "height": "250",
                    "placeholder": "<br><br>Add any additional notes here.",
                }
            }
        )
    )
    additional_info = forms.CharField(
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "height": "250",
                    "placeholder": "<br><br>Add any additional notes here. This appears at the bottom of the page and is not inside a box.",
                }
            }
        )
    )
    bank_transfer_details = forms.CharField(
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "height": "250",
                    "placeholder": "<br><br>This appears for people who pay by bank transfer. Specify the account details for your bank and any reference you would like attached.",
                }
            }
        )
    )
    cheque_details = forms.CharField(
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "height": "250",
                    "placeholder": "<br><br>This appears for people who pay by cheque. Specify who to make the cheque payable to and where to send it.",
                }
            }
        )
    )

    def clean_allow_youth_payment_discount(self):
        if self.cleaned_data["allow_youth_payment_discount"] and (
            self.cleaned_data.get("youth_payment_discount_date", None) is None
        ):
            raise ValidationError(
                'If "Give Youth Entry Discount" is checked then you must enter the youth cutoff date'
            )
        return self.cleaned_data["allow_youth_payment_discount"]

    def clean_allow_early_payment_discount(self):
        early_payment_discount = self.cleaned_data["allow_early_payment_discount"]
        if early_payment_discount and (
            self.cleaned_data.get("early_payment_discount_date", None) is None
        ):
            raise ValidationError(
                'If "Give Early Entry Discount" is checked, then you must enter last date for discount'
            )
        return early_payment_discount

    class Meta:
        model = Congress
        fields = (
            "congress_master",
            "year",
            "name",
            "start_date",
            "end_date",
            "date_string",
            "venue_name",
            "venue_location",
            "venue_transport",
            "venue_catering",
            "venue_additional_info",
            "additional_info",
            "people",
            "raw_html",
            "general_info",
            "links",
            "sponsors",
            "payment_method_system_dollars",
            "payment_method_bank_transfer",
            "payment_method_cash",
            "payment_method_cheques",
            "payment_method_off_system_pp",
            "entry_open_date",
            "entry_close_date",
            "allow_partnership_desk",
            "senior_date",
            "senior_age",
            "youth_payment_discount_date",
            "youth_payment_discount_age",
            "early_payment_discount_date",
            "allow_youth_payment_discount",
            "allow_early_payment_discount",
            "bank_transfer_details",
            "cheque_details",
            "automatic_refund_cutoff",
            "congress_type",
            "contact_email",
            "congress_venue_type",
            "online_platform",
            # "automatically_mark_club_pp_as_paid",
        )


class NewCongressForm(forms.Form):
    def __init__(self, *args, **kwargs):

        # Get valid orgs as parameter
        valid_orgs = kwargs.pop("valid_orgs", [])
        super().__init__(*args, **kwargs)

        org_queryset = Organisation.objects.filter(pk__in=valid_orgs).order_by("name")
        choices = [("", "-----------")]
        for item in org_queryset:
            choices.append((item.pk, item.name))
        self.fields["org"].choices = choices

    org = forms.ChoiceField(label="Organisation", required=False)
    congress_master = forms.IntegerField(label="Organisation", required=False)
    congress = forms.IntegerField(label="Organisation", required=False)


class EventForm(forms.ModelForm):

    entry_close_time = forms.TimeField(
        input_formats=[
            "%H:%M",
        ],
        required=False,
    )

    class Meta:
        model = Event
        fields = (
            "event_name",
            "description",
            "max_entries",
            "event_type",
            "entry_open_date",
            "entry_close_date",
            "entry_close_time",
            "player_format",
            "entry_fee",
            "entry_early_payment_discount",
            "entry_youth_payment_discount",
            "free_format_question",
            "allow_team_names",
            "list_priority_order",
        )

    def clean_entry_early_payment_discount(self):
        data = self.cleaned_data["entry_early_payment_discount"]
        if data is None:
            return 0.0
        return data

    def clean_entry_youth_payment_discount(self):
        """If we have a youth discount then check it is a positive number"""

        entry_youth_payment_discount = self.cleaned_data["entry_youth_payment_discount"]
        if entry_youth_payment_discount and entry_youth_payment_discount < 0:
            self.add_error(
                "entry_youth_payment_discount", "Discount percentage cannot be negative"
            )

        return entry_youth_payment_discount


class SessionForm(forms.ModelForm):
    class Meta:
        model = Session
        fields = (
            "session_date",
            "session_start",
            "session_end",
        )


class CongressMasterForm(forms.ModelForm):
    class Meta:
        model = CongressMaster
        fields = (
            "name",
            "org",
        )


class EventEntryPlayerForm(forms.ModelForm):
    class Meta:
        model = EventEntryPlayer
        fields = (
            "payment_type",
            "payment_status",
            "entry_fee",
            "payment_received",
            "reason",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # We can get problems if the convener changes the payment method to their-bridge-credits
        # This is intended for use with team-mates plus and none of the controls will be in place
        # if it gets manually changed by a convener.
        # There is no reason for this to be required so remove from options unless already set.
        if self.initial["payment_type"] != "their-system-dollars":
            choices = self.fields["payment_type"].choices
            clean_choices = [
                choice for choice in choices if choice[0] != "their-system-dollars"
            ]

            self.fields["payment_type"].choices = clean_choices

    def clean_entry_fee(self):
        entry_fee = self.cleaned_data["entry_fee"]
        if type(entry_fee) is not Decimal or entry_fee < 0:
            raise ValidationError("Entry fee must be a positive number or zero")
        return entry_fee


class EventEntryPlayerTBAForm(forms.ModelForm):
    """Handle changing the TBA data (manual override)"""

    class Meta:
        model = EventEntryPlayer
        fields = (
            "override_tba_name",
            "override_tba_system_number",
        )


class RefundForm(forms.Form):

    player_id = forms.IntegerField()
    player = forms.CharField(max_length=100)
    refund = forms.DecimalField()


class EventPlayerDiscountForm(forms.ModelForm):
    class Meta:
        model = EventPlayerDiscount
        fields = (
            "player",
            "reason",
            "entry_fee",
        )


class EmailForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Hide the crispy labels
        self.fields["body"].label = False

    subject = forms.CharField(max_length=100)
    body = forms.CharField(
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "height": "250",
                    "codemirror": {"theme": "monokai"},
                    "placeholder": "<br><br>Enter the body of your email. You can use the test button as many times as you like.",
                }
            }
        )
    )

    def clean_body(self):
        # Clean the data - we get some stuff through from cut and paste that messes up emails
        body = self.cleaned_data["body"]

        body = bleach.clean(
            body,
            strip=True,
            tags=BLEACH_ALLOWED_TAGS,
            attributes=BLEACH_ALLOWED_ATTRIBUTES,
            styles=BLEACH_ALLOWED_STYLES,
        )

        body = body.replace("<", "\n<")

        return body


class LatestNewsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Hide the crispy labels
        self.fields["latest_news"].label = False

    latest_news = forms.CharField(
        required=False,
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "height": "250",
                    "placeholder": "<br><br>Enter the latest news for the top of your homepage. If this is blank it will be skipped. If you overwrite what is in here it will be lost.",
                }
            }
        ),
    )


class BulletinForm(forms.ModelForm):
    class Meta:
        model = Bulletin
        fields = ("document", "congress", "description")


class CongressDownloadForm(forms.ModelForm):
    class Meta:
        model = CongressDownload
        fields = ("document", "congress", "description")


class PartnershipForm(forms.ModelForm):
    class Meta:
        model = PartnershipDesk
        fields = ("event", "private", "comment", "player")


class OffSystemPPForm(forms.Form):
    """For off system PP payments"""

    CARD_CHOICES = [
        ("Dummy", "Dummy"),
    ]

    # Handle checkboxes
    event_entry_players_list = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        choices=CARD_CHOICES,
    )

    def __init__(self, *args, **kwargs):
        """dynamic override of checkbox list"""

        # Get list of event_entry_players
        self.event_entry_players = kwargs.pop("event_entry_players", None)
        super().__init__(*args, **kwargs)
        self.fields["event_entry_players_list"].choices = self.event_entry_players
