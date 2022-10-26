from django import forms


class SystemSettingsForm(forms.Form):
    """system settings from AWS"""

    disable_playpen = forms.BooleanField(
        required=False, label="Disable Playpen (allow emails to leave test systems)"
    )
    maintenance_mode = forms.BooleanField(
        required=False, label="Maintenance Mode (prevent users from accessing system)"
    )
