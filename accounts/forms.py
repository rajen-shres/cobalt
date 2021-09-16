""" Forms for Accounts App """

from PIL import Image
import re
import datetime

from crispy_forms.helper import FormHelper
from django import forms
from django.contrib.auth.forms import UserCreationForm

from cobalt.settings import GLOBAL_ORG
from masterpoints.views import system_number_available
from .models import User, UnregisteredUser
from django.core.exceptions import ValidationError

import accounts.views as accounts_views


class UserRegisterForm(UserCreationForm):
    """User Registration"""

    email = forms.EmailField()

    class Meta:
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
        if not username:
            raise forms.ValidationError("System number missing")

        if not system_number_available(username):
            raise forms.ValidationError("Number invalid or in use")
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_show_labels = False
        self.old_dob = kwargs["instance"].dob
        print("old DOB:", self.old_dob)

    def clean_dob(self):
        # DOB will be None if invalid data was entered. We can only really fix this
        # with some JavaScript code or by making DOB required. This works for all
        # cases except when an invalid date is entered along with other valid data
        if not self.changed_data:
            # No changes detected but form was submitted - will be due to an invalid date
            return self._clean_dob_sub("Date of birth was invalid. Try again.")

        dob = self.cleaned_data["dob"]
        if "dob" in self.changed_data and not dob:
            return self._clean_dob_sub("Date of birth was invalid.")
        if dob is None:
            return None
        if dob > datetime.datetime.today().date():
            # raise ValidationError("Date of birth must be earlier than today.")
            self.add_error("dob", "Date of birth must be earlier than today.")
        if dob.year < 1900:
            self.add_error("dob", "Date of birth must be after 1900.")
        return dob

    def _clean_dob_sub(self, error):

        self.add_error("dob", error)
        self.data = self.data.copy()
        self.data["dob"] = self.old_dob
        return self.old_dob

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


class UnregisteredUserForm(forms.ModelForm):
    """Form to edit an Unregistered User"""

    class Meta:
        model = UnregisteredUser
        fields = [
            "system_number",
            "first_name",
            "last_name",
            "email",
        ]

    def clean_system_number(self):

        system_number = self.cleaned_data["system_number"]

        is_valid, is_member, is_un_reg = accounts_views.check_system_number(
            system_number
        )

        if not is_valid:
            self.add_error("system_number", f"{GLOBAL_ORG} Number invalid")
        if is_member:
            self.add_error(
                "system_number", f"{GLOBAL_ORG} Number in use for a registered member"
            )

        return system_number
