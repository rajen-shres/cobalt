""" Forms for Accounts App """

from PIL import Image
import re
import datetime

from crispy_forms.helper import FormHelper
from django import forms
from django.contrib.auth.forms import UserCreationForm
from masterpoints.views import system_number_available
from .models import User
from django.core.exceptions import ValidationError


class UserRegisterForm(UserCreationForm):
    """User Registration"""

    email = forms.EmailField()

    class Meta:
        """Meta data"""

        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "system_number",
            "mobile",
            "password1",
            "password2",
        ]

    def clean_username(self):
        """check system_number is valid. Don't rely on client side validation"""

        username = self.cleaned_data["username"]
        if username:
            if not system_number_available(username):
                raise forms.ValidationError("Number invalid or in use")
        else:
            raise forms.ValidationError("System number missing")

        return username


class UserUpdateForm(forms.ModelForm):
    """Used by Profile to update details"""

    class Meta:
        """Meta data"""

        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "system_number",
            "dob",
            "mobile",
            "pic",
            "bbo_name",
        ]

        # widgets = {
        #     'dob': forms.DateInput(format='%Y-%m-%d')
        # }

    def __init__(self, *args, **kwargs):
        super(UserUpdateForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_show_labels = False

    def clean_dob(self):
        dob = self.cleaned_data["dob"]
        if dob is None:
            return None
        if dob > datetime.datetime.today().date():
            # raise ValidationError("Date of birth must be earlier than today.")
            self.add_error("dob", "Date of birth must be earlier than today.")
        print(dob)
        return dob

    def clean_mobile(self):
        """
        if you add spaces between number then they are replaced here
        """
        mobile_raw = self.cleaned_data["mobile"]
        if mobile_raw is None:
            return None
        mobile = mobile_raw.replace(" ", "")
        mobile_regex = r"^[\+0]?1?\d{9,15}$"
        if re.match(mobile_regex, mobile):
            return mobile
        else:
            raise ValidationError(
                "Mobile number should be either starting with + or 0 and should be between 9-15 digits long"
            )


class PhotoUpdateForm(forms.ModelForm):
    """Handles the sub-form on profile for picture"""

    x = forms.FloatField(widget=forms.HiddenInput())
    y = forms.FloatField(widget=forms.HiddenInput())
    width = forms.FloatField(widget=forms.HiddenInput())
    height = forms.FloatField(widget=forms.HiddenInput())

    class Meta:
        """Meta data"""

        model = User
        fields = (
            "pic",
            "x",
            "y",
            "width",
            "height",
        )
        widgets = {"file": forms.FileInput(attrs={"accept": "image/*"})}

    def save(self):
        photo = super(PhotoUpdateForm, self).save()

        x = self.cleaned_data.get("x")
        y = self.cleaned_data.get("y")
        w = self.cleaned_data.get("width")
        h = self.cleaned_data.get("height")

        image = Image.open(photo.pic)
        cropped_image = image.crop((x, y, w + x, h + y))
        resized_image = cropped_image.resize((200, 200), Image.ANTIALIAS)
        resized_image.save(photo.pic.path)

        return photo


class BlurbUpdateForm(forms.ModelForm):
    """Handles the sub-form on profile for wordage"""

    class Meta:
        """Meta data"""

        model = User
        fields = ("about",)


class UserSettingsForm(forms.ModelForm):
    """Used by Settings to update details"""

    class Meta:
        """Meta data"""

        model = User
        fields = [
            "username",
            "receive_sms_results",
            "receive_sms_reminders",
            "receive_abf_newsletter",
            "receive_marketing",
            "receive_monthly_masterpoints_report",
            "receive_payments_emails",
            "system_number_search",
            "windows_scrollbar",
        ]
