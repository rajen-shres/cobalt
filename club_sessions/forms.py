from django import forms
from django_summernote.widgets import SummernoteInplaceWidget

from accounts.models import UnregisteredUser, User
from club_sessions.views.core import PLAYING_DIRECTOR, SITOUT, VISITOR
from club_sessions.models import Session, SessionType, SessionEntry
from cobalt.settings import BRIDGE_CREDITS
from organisations.models import OrgVenue, MemberMembershipType
from payments.models import OrgPaymentMethod


class SessionForm(forms.ModelForm):
    """Session Form"""

    class Meta:
        model = Session
        fields = [
            "director",
            "session_type",
            "session_date",
            "description",
            "venue",
            "time_of_day",
            "additional_session_fee",
            "additional_session_fee_reason",
            "default_secondary_payment_method",
            "director_notes",
        ]

    director_notes = forms.CharField(
        required=False,
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "height": "250",
                    "placeholder": "<br><br>(Optional) Placeholder for notes about the session",
                }
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        # Get club parameter so we can build correct choice lists
        club = kwargs.pop("club", None)

        # Call Super()
        super().__init__(*args, **kwargs)

        # See if there are venues
        venues = OrgVenue.objects.filter(organisation=club, is_active=True).values_list(
            "id", "venue"
        )
        if venues.count() > 0:
            self.fields["venue"].choices = venues
        else:
            del self.fields["venue"]

        # Handle session types
        session_types = SessionType.objects.filter(
            organisation=club, status=True
        ).values_list("id", "name")
        if session_types.count() > 0:
            self.fields["session_type"].choices = session_types
        else:
            self.fields["session_type"].choices = [
                ("", "Error - No session types defined")
            ]

        # Handle default_secondary_payment_methods
        org_payment_types = (
            OrgPaymentMethod.objects.filter(organisation=club, active=True)
            .exclude(payment_method="Bridge Credits")
            .values_list("id", "payment_method")
        )
        self.fields["default_secondary_payment_method"].choices = org_payment_types
        if club.default_secondary_payment_method:
            self.fields[
                "default_secondary_payment_method"
            ].initial = club.default_secondary_payment_method.id

    # def clean_session_type(self):
    #     """ validate session type - don't allow changes if payments made """
    #
    #     if SessionEntry.objects.filter(
    #         session=self.instance, is_paid=True
    #     ).exists():
    #         self.add_error('session_type', "Cannot change session type as payments have been made")


class UserSessionForm(forms.Form):
    """Form for the screen to allow editing a single user in a session
    Has a bit of a mixture of things on it from multiple places
    """

    fee = forms.DecimalField(min_value=0)
    is_paid = forms.BooleanField(label="Is Processed", required=False)
    payment_method = forms.ChoiceField()

    def __init__(self, *args, **kwargs):
        # Get parameters
        club = kwargs.pop("club", None)
        session_entry = kwargs.pop("session_entry", None)

        # Call Super()
        super().__init__(*args, **kwargs)

        # Abuse the form to add some other fields to it

        # See if user is a member
        self.membership_type = (
            MemberMembershipType.objects.filter(
                system_number=session_entry.system_number
            )
            .filter(membership_type__organisation=club)
            .exclude(system_number__in=[PLAYING_DIRECTOR, SITOUT, VISITOR])
            .first()
        )

        self.is_member = self.membership_type is not None

        # Try to load User - Note: Player may end up as a User or an Unregistered User
        self.player = (
            User.objects.filter(system_number=session_entry.system_number)
            .exclude(system_number__in=[PLAYING_DIRECTOR, SITOUT, VISITOR])
            .first()
        )

        # Try to load un_reg if not a member
        if self.player:
            self.is_user = True
            self.is_valid_number = True
            self.player_type = "Registered User"
        else:
            self.player = UnregisteredUser.objects.filter(
                system_number=session_entry.system_number
            ).first()
            self.is_user = False

            # See if this is even a valid system_number, if neither are true. Usually we add the un_reg automatically
            if self.player:
                self.is_un_reg = True
                self.is_valid_number = True
                self.player_type = "Unregistered User"
                # self.fields["player_no"].initial = self.player.id
            # else:
            #     # TODO: Add later
            #     invalid_number = True

        # Add values
        self.fields["fee"].initial = session_entry.fee
        self.fields["is_paid"].initial = session_entry.is_paid

        # Get payment method choices
        all_payment_methods = OrgPaymentMethod.objects.filter(
            organisation=club, active=True
        ).values_list("id", "payment_method")

        # Only allow Bridge Credits and IOUs for real users
        payment_methods = []
        for all_payment_method in all_payment_methods:
            if self.is_user or all_payment_method[1] not in [BRIDGE_CREDITS, "IOU"]:
                payment_methods.append(all_payment_method)

        self.fields["payment_method"].choices = payment_methods
        if session_entry.payment_method:
            self.fields["payment_method"].initial = session_entry.payment_method.id


class FileImportForm(forms.Form):
    """Session file upload form"""

    file = forms.FileField()
