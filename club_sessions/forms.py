from django import forms
from django.db.models import Q

from accounts.models import UnregisteredUser, User
from club_sessions.models import Session, SessionType
from organisations.models import OrgVenue, MemberMembershipType
from organisations.views.general import get_membership_type_for_players
from payments.models import OrgPaymentMethod, UserPendingPayment


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
        ]

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


class UserSessionForm(forms.Form):
    """Form for the screen to allow editing a single user in a session
    Has a bit of a mixture of things on it from multiple places
    """

    fee = forms.DecimalField(min_value=0)
    amount_paid = forms.DecimalField(min_value=0)
    payment_method = forms.ChoiceField()
    player_no = forms.IntegerField()

    def __init__(self, *args, **kwargs):
        # Get parameters
        club = kwargs.pop("club", None)
        session_entry = kwargs.pop("session_entry", None)

        # Call Super()
        super().__init__(*args, **kwargs)

        # Abuse the form to add some other fields to it

        # See if user is a member
        self.membership_type = (
            MemberMembershipType.objects.active()
            .filter(system_number=session_entry.system_number)
            .filter(membership_type__organisation=club)
            .first()
        )

        self.is_member = self.membership_type is not None

        # Try to load User - Note: Player may end up as a User or an Unregistered User
        self.player = User.objects.filter(
            system_number=session_entry.system_number
        ).first()

        # Try to load un_reg if not a member
        if self.player:
            self.is_user = True
            self.is_valid_number = True
            self.player_type = "Registered User"
            self.fields["player_no"].initial = self.player.id
        else:
            self.player = UnregisteredUser.objects.filter(
                system_number=session_entry.system_number
            ).first()

            # See if this is even a valid system_number, if neither are true. Usually we add the un_reg automatically
            if self.player:
                self.is_un_reg = True
                self.is_valid_number = True
                self.player_type = "Unregistered User"
                self.fields["player_no"].initial = self.player.id
            # else:
            #     # TODO: Add later
            #     invalid_number = True

        # Add values
        self.fields["fee"].initial = session_entry.fee
        self.fields["amount_paid"].initial = session_entry.amount_paid

        # Get payment method choices
        payment_methods = OrgPaymentMethod.objects.filter(
            organisation=club, active=True
        ).values_list("id", "payment_method")
        self.fields["payment_method"].choices = payment_methods
        if session_entry.payment_method:
            self.fields["payment_method"].initial = session_entry.payment_method.id

        # Check for IOUs
        self.user_pending_payments = UserPendingPayment.objects.filter(
            system_number=session_entry.system_number
        ).filter(organisation=club)


class FileImportForm(forms.Form):
    """Session file upload form"""

    file = forms.FileField()
