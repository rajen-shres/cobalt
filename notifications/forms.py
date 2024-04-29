import bleach
from django import forms
from django_summernote.widgets import SummernoteInplaceWidget

from cobalt.settings import (
    BLEACH_ALLOWED_TAGS,
    BLEACH_ALLOWED_ATTRIBUTES,
    BLEACH_ALLOWED_STYLES,
)
from organisations.models import OrgEmailTemplate
from notifications.models import EmailAttachment


class EmailContactForm(forms.Form):
    """Contact a member"""

    title = forms.CharField(label="Title", max_length=80)
    message = forms.CharField(label="Message")
    redirect_to = forms.CharField(label="Redirect_To")


class MemberToMemberEmailForm(forms.Form):
    """Contact a member"""

    subject = forms.CharField(max_length=80)
    message = forms.CharField(
        # THESE ARE OVERRIDDEN IN THE TEMPLATE
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "height": "400",
                    "codemirror": {"theme": "monokai"},
                    "placeholder": "<br><br>Enter your message.",
                }
            }
        )
    )

    redirect_to = forms.CharField(label="Redirect_To")


class OrgEmailForm(forms.Form):
    """Form to send an email using a template. This form doesn't include who to send it to,
    that is specific to the use of the form and needs to be handled separately"""

    subject = forms.CharField(max_length=100)
    org_email_body = forms.CharField(
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "height": "400",
                    "codemirror": {"theme": "monokai"},
                    "placeholder": "<br><br>Enter the body of your email. You can use the test button as many times as you like.",
                }
            }
        )
    )
    reply_to = forms.EmailField(max_length=100, required=False)
    from_name = forms.CharField(max_length=100, required=False)
    template = forms.ChoiceField(required=False)

    def __init__(self, *args, **kwargs):
        """create list of templates"""

        # Get club
        self.club = kwargs.pop("club", None)
        super().__init__(*args, **kwargs)

        # Only show this club's templates
        choices = [
            (choice.pk, choice.template_name)
            for choice in OrgEmailTemplate.objects.filter(organisation=self.club)
        ]
        self.fields["template"].choices = choices

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


class AddContactForm(forms.Form):
    """Simple form to get details of a contact"""

    first_name = forms.CharField(label="First name", max_length=100, required=False)
    last_name = forms.CharField(label="Last name", max_length=100, required=False)
    email = forms.EmailField(label="Email", max_length=100, required=True)


class EmailOptionsForm(forms.Form):
    """Form to get email options (compose email step 2)"""

    reply_to = forms.EmailField(max_length=100, required=False)
    from_name = forms.CharField(max_length=100, required=False)
    template = forms.ChoiceField(required=False)

    def __init__(self, *args, **kwargs):
        """create list of templates"""

        # Get club
        self.club = kwargs.pop("club", None)
        super().__init__(*args, **kwargs)

        # Only show this club's templates
        choices = [
            (choice.pk, choice.template_name)
            for choice in OrgEmailTemplate.objects.filter(organisation=self.club)
        ]

        self.fields["template"].choices = choices

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


class EmailContentForm(forms.Form):
    """Form to get email content (compose email step 3)"""

    subject = forms.CharField(max_length=100)
    email_body = forms.CharField(
        label="Email Body",
        widget=SummernoteInplaceWidget(
            attrs={
                "summernote": {
                    "height": "400",
                    "codemirror": {"theme": "monokai"},
                    "placeholder": "<br><br>Enter the body of your email. You can use the test button as many times as you like.",
                }
            }
        ),
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


class EmailAttachmentForm(forms.ModelForm):
    """Form for uploading an attachment for a club"""

    class Meta:

        model = EmailAttachment
        fields = ("attachment",)
        widgets = {"attachment": forms.FileInput(attrs={"accept": "*/*"})}
