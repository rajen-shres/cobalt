from django import forms


class ContactForm(forms.Form):
    """ Contact Support """

    title = forms.CharField(label="Title", max_length=80)
    message = forms.CharField(label="Message")
