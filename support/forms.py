from django import forms

from rbac.core import rbac_get_users_with_role
from support.models import Incident, Attachment, IncidentLineItem, NotifyUserByType
from django_summernote.widgets import SummernoteInplaceWidget


class ContactForm(forms.Form):
    """Contact Support"""

    title = forms.CharField(label="Title", max_length=80)
    message = forms.CharField(label="Message")
    username = forms.CharField(label="User name")
    email = forms.CharField(label="email(required if not logged in)")


class HelpdeskLoggedInContactForm(forms.ModelForm):
    """Contact form for users who are logged in"""

    class Meta:
        model = Incident
        fields = ("title", "description", "reported_by_user", "incident_type")


class HelpdeskLoggedOutContactForm(forms.ModelForm):
    """Contact form for users who are logged out"""

    class Meta:
        model = Incident
        fields = (
            "reported_by_name",
            "reported_by_email",
            "title",
            "incident_type",
            "description",
        )
        labels = {
            "incident_type": "Area",
            "title": "Subject",
            "reported_by_email": "Your email address",
            "reported_by_name": "Your name",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # require fields
        self.fields["title"].required = True
        self.fields["description"].required = True
        self.fields["reported_by_email"].required = True
        self.fields["reported_by_name"].required = True


class IncidentForm(forms.ModelForm):
    """Create a new helpdesk ticket"""

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
        """override init so we can set the assigned_to field to be only support staff"""
        super().__init__(*args, **kwargs)

        staff = [(None, "Unassigned")] + list(
            rbac_get_users_with_role("support.helpdesk.edit").values_list(
                "id", "first_name"
            )
        )
        self.fields["assigned_to"].choices = staff

    def clean(self):
        """custom validation"""
        cleaned_data = super(IncidentForm, self).clean()

        if not (
            cleaned_data.get("reported_by_user")
            or cleaned_data.get("reported_by_email")
        ):
            txt = "Either user or email are required"
            self._errors["reported_by_user"] = txt
            raise forms.ValidationError(txt)
        return self.cleaned_data


class AttachmentForm(forms.ModelForm):
    class Meta:
        model = Attachment
        fields = ("document", "incident", "description", "user")


class IncidentLineItemForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        # Hide the crispy labels
        self.fields["description"].label = False

    description = forms.CharField(
        widget=SummernoteInplaceWidget(
            attrs={"summernote": {"placeholder": "<br><br>Add Comment..."}}
        )
    )
    action = forms.ChoiceField(
        choices=[
            ("add-comment", "Add Comment"),
            ("add-close", "Add Comment and Close Ticket"),
            ("add-close-silent", "Add Comment and Close Ticket (don't notify user)"),
            ("add-awaiting", "Add Comment and set to awaiting user feedback"),
        ]
    )

    class Meta:
        model = IncidentLineItem
        fields = ("description",)


class NotifyUserByTypeForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        # Hide the crispy labels
        self.fields["incident_type"].label = False

    def clean(self):
        """custom validation"""
        cleaned_data = super(NotifyUserByTypeForm, self).clean()

        incident_type = cleaned_data.get("incident_type")
        staff = cleaned_data.get("staff")

        # Lets clean up if all is specified
        if incident_type == "All":
            NotifyUserByType.objects.filter(staff=staff).delete()
        else:
            if (
                NotifyUserByType.objects.filter(incident_type="All")
                .filter(staff=staff)
                .exists()
            ):
                txt = "There is already an All setting for this user"
                self._errors["staff"] = txt
                raise forms.ValidationError(txt)
            if (
                NotifyUserByType.objects.filter(incident_type=incident_type)
                .filter(staff=staff)
                .exists()
            ):
                txt = f"There is already a setting for {incident_type} for this user"
                self._errors["staff"] = txt
                raise forms.ValidationError(txt)
        return self.cleaned_data

    class Meta:
        model = NotifyUserByType
        fields = ("incident_type", "staff")
