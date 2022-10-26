from django import forms


class SystemSettingsForm(forms.Form):
    """system settings from AWS"""

    fish_setting = forms.BooleanField(required=False)
    disable_playpen = forms.BooleanField(required=False)
    maintenance_mode = forms.BooleanField(required=False)
