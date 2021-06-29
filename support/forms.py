from django import forms

from rbac.core import rbac_get_users_with_role
from support.models import Incident


class ContactForm(forms.Form):
    """ Contact Support """

    title = forms.CharField(label="Title", max_length=80)
    message = forms.CharField(label="Message")
    username = forms.CharField(label="User name")
    email = forms.CharField(label="email(required if not logged in)")


class IncidentForm(forms.ModelForm):
    """ Create a new helpdesk ticket """

    class Meta:
        model = Incident
        fields = (
            "title",
            "assigned_to",
            "reported_by_email",
            "description",
            "status",
            "incident_type",
            "reported_by_user",
            "reported_by_name",
            "severity",
        )

    def __init__(self, *args, **kwargs):
        """ override init so we can set the assigned_to field to be only support staff"""
        super(IncidentForm, self).__init__(*args, **kwargs)

        staff = [(None, "Unassigned")] + list(
            rbac_get_users_with_role("support.helpdesk.edit").values_list(
                "id", "first_name"
            )
        )
        self.fields["assigned_to"].choices = staff

    def clean(self):
        """ custom validation """
        cleaned_data = super(IncidentForm, self).clean()

        print(cleaned_data.get("reported_by_user"))
        print(cleaned_data.get("reported_by_email"))
        if not (
            cleaned_data.get("reported_by_user")
            or cleaned_data.get("reported_by_email")
        ):
            txt = "Either user or email are required"
            self._errors["reported_by_user"] = txt
            raise forms.ValidationError(txt)
        return self.cleaned_data
