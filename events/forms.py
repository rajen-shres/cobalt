from django import forms
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
from cobalt.settings import GLOBAL_ORG, GLOBAL_CURRENCY_NAME, BRIDGE_CREDITS


class CongressForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):

        # Get allowed congress masters as parameter
        congress_masters = kwargs.pop("congress_masters", [])
        super(CongressForm, self).__init__(*args, **kwargs)

        # Modify and congress master if  passed
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
            "allow_early_payment_discount",
            "senior_date",
            "senior_age",
            "youth_payment_discount_date",
            "youth_payment_discount_age",
            "allow_youth_payment_discount",
            "early_payment_discount_date",
            "bank_transfer_details",
            "cheque_details",
            "automatic_refund_cutoff",
        )


class NewCongressForm(forms.Form):
    def __init__(self, *args, **kwargs):

        # Get valid orgs as parameter
        valid_orgs = kwargs.pop("valid_orgs", [])
        super(NewCongressForm, self).__init__(*args, **kwargs)

        org_queryset = Organisation.objects.filter(pk__in=valid_orgs).order_by("name")
        choices = [("", "-----------")]
        for item in org_queryset:
            choices.append((item.pk, item.name))
        self.fields["org"].choices = choices

    org = forms.ChoiceField(label="Organisation", required=False)
    congress_master = forms.IntegerField(label="Organisation", required=False)
    congress = forms.IntegerField(label="Organisation", required=False)


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = (
            "event_name",
            "description",
            "max_entries",
            "event_type",
            "entry_open_date",
            "entry_close_date",
            "player_format",
            "entry_fee",
            "entry_early_payment_discount",
            "entry_youth_payment_discount",
            "free_format_question",
        )


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
            "player",
            "payment_type",
            "payment_status",
            "entry_fee",
            "payment_received",
            "reason",
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
        super(EmailForm, self).__init__(*args, **kwargs)

        # Hide the crispy labels
        self.fields["body"].label = False

    subject = forms.CharField(max_length=100)
    body = forms.CharField(
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "height": "250",
                    "placeholder": "<br><br>Enter the body of your email. Do not insert pictures as they will not work.",
                }
            }
        )
    )


class LatestNewsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super(LatestNewsForm, self).__init__(*args, **kwargs)

        # Hide the crispy labels
        self.fields["latest_news"].label = False

    latest_news = forms.CharField(
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "height": "250",
                    "placeholder": "<br><br>Enter the latest news for the top of your homepage. If this is blank it will be skipped. If you overwrite what is in here it will be lost.",
                }
            }
        )
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
    """ For off system PP payments """

    CARD_CHOICES = [
        ("Dummy", "Dummy"),
    ]

    # Handle checkboxes
    event_entry_players_list = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple, choices=CARD_CHOICES,
    )

    def __init__(self, *args, **kwargs):
        """ dynamic override of checkbox list """

        # Get list of event_entry_players
        self.event_entry_players = kwargs.pop("event_entry_players", None)
        super(OffSystemPPForm, self).__init__(*args, **kwargs)
        self.fields["event_entry_players_list"].choices = self.event_entry_players
