import bleach
from django import forms
from django_summernote.widgets import SummernoteInplaceWidget

from cobalt.settings import (
    BLEACH_ALLOWED_TAGS,
    BLEACH_ALLOWED_ATTRIBUTES,
    BLEACH_ALLOWED_STYLES,
)


class EmailContactForm(forms.Form):
    """Contact a member"""

    title = forms.CharField(label="Title", max_length=80)
    message = forms.CharField(label="Message")
    redirect_to = forms.CharField(label="Redirect_To")


class EmailForm(forms.Form):
    """Form to send an email. This form doesn't include who to send it to, that is specific to the use of the form
    and needs to be handled separately"""

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
    reply_to = forms.CharField(max_length=100, required=False)

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
