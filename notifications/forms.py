from django import forms


class EmailContactForm(forms.Form):
    """ Contact a member """

    title = forms.CharField(label="Title", max_length=80)
    message = forms.CharField(label="Message")
