""" Forms for Accounts App """

from PIL import Image
import re
import datetime

from crispy_forms.helper import FormHelper
from django import forms
from django.contrib.auth.forms import UserCreationForm

import accounts.views.admin
from cobalt.settings import GLOBAL_ORG
from masterpoints.factories import masterpoint_factory_creator
from .models import User, UnregisteredUser
from django.core.exceptions import ValidationError


class UserRegisterForm(UserCreationForm):
    """User Registration"""

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

    def clean(self):
        """The validation will reject a duplicate user. We want to allow is_active=False users
        to sign up again.

        This doesn't affect field level validations
        """
        pass

    def clean_username(self):
        """Final check that system number is valid and available. System_number is submitted as username"""
        system_number = self.cleaned_data["username"]
        mp_source = masterpoint_factory_creator()
        if mp_source.system_number_valid(system_number):
            return system_number

        raise ValidationError(f"{GLOBAL_ORG} number invalid or in use")

    def clean_first_name(self):
        first_name = self.cleaned_data["first_name"]
        if not first_name or first_name == "":
            raise ValidationError("First name missing.")
        return first_name

    def clean_last_name(self):
        last_name = self.cleaned_data["last_name"]
        if not last_name or last_name == "":
            raise ValidationError("Last name missing.")
        return last_name


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

    def clean_dob(self):

        dob = self.cleaned_data["dob"]
        if "dob" in self.changed_data and not dob:
            return self._clean_dob_sub("Date of birth is invalid.")
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
        mobile_regex = r"^04\d{8}$"
        if re.match(mobile_regex, mobile):
            return mobile
        else:
            raise ValidationError(
                "We only accept Australian phone numbers starting 04 which are 10 numbers long."
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
            "first_name",
            "last_name",
            "email",
        ]

    def clean_system_number(self):

        system_number = self.cleaned_data["system_number"]

        (
            is_valid,
            is_member,
            is_un_reg,
        ) = accounts.views.admin.check_system_number(system_number)

        if not is_valid:
            self.add_error("system_number", f"{GLOBAL_ORG} Number invalid")
        if is_member:
            self.add_error(
                "system_number", f"{GLOBAL_ORG} Number in use for a registered member"
            )

        return system_number
