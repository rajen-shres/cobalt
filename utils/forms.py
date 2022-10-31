from django import forms


class SystemSettingsForm(forms.Form):
    """system settings from AWS"""

    disable_playpen = forms.BooleanField(
        required=False, label="Disable Playpen (allow emails to leave test systems)"
    )
    debug_flag = forms.BooleanField(
        required=False, label="Debug (show better errors in test environments)"
    )
    maintenance_mode = forms.BooleanField(
        required=False, label="Maintenance Mode (prevent users from accessing system)"
    )
