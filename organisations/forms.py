from django import forms
from .models import Organisation


class OrgForm(forms.ModelForm):
    class Meta:
        model = Organisation
        fields = (
            "name",
            "address1",
            "address2",
            "suburb",
            "state",
            "postcode",
            "bank_bsb",
            "bank_account",
        )
