from django import forms

from club_sessions.models import Session, SessionType
from organisations.models import OrgVenue


class SessionForm(forms.ModelForm):
    """Session Form"""

    class Meta:
        model = Session
        fields=[
            'director',
            'session_type',
            'session_date',
            'description',
            'venue',
            'time_of_day',
        ]

    def __init__(self, *args, **kwargs):
        # Get club parameter so we can build correct choice lists
        club = kwargs.pop("club", None)

        # Call Super()
        super().__init__(*args, **kwargs)

        # See if there are venues
        venues = OrgVenue.objects.filter(organisation=club, is_active=True).values_list("id", "venue")
        if venues.count() > 0:
            self.fields['venue'].choices = venues
        else:
            del self.fields['venue']

        # Handle session types
        session_types = SessionType.objects.filter(organisation=club, status=True).values_list("id", "name")
        if session_types.count() > 0:
            self.fields['session_type'].choices = session_types
        # else:
        #     self.add_error('session_type', "No session types defined")

