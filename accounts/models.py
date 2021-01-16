""" Models for our definitions of a user within the system. """

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, RegexValidator
from cobalt.settings import AUTO_TOP_UP_MAX_AMT, GLOBAL_ORG, TBA_PLAYER, RBAC_EVERYONE
from PIL import Image


class User(AbstractUser):
    """
    User class based upon AbstractUser.
    """

    email = models.EmailField(unique=False)
    system_number = models.IntegerField(
        "%s Number" % GLOBAL_ORG, blank=True, unique=True
    )

    phone_regex = RegexValidator(
        regex=r"^\+?1?\d{9,15}$",
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.",
    )
    mobile = models.CharField(
        "Mobile Number",
        blank=True,
        unique=True,
        null=True,
        max_length=15,
        validators=[phone_regex],
    )
    about = models.TextField("About Me", blank=True, null=True, max_length=800)
    pic = models.ImageField(
        upload_to="pic_folder/", default="pic_folder/default-avatar.png"
    )
    dob = models.DateField(blank="True", null=True)
    bbo_name = models.CharField("BBO Username", blank=True, null=True, max_length=20)
    auto_amount = models.PositiveIntegerField(
        "Auto Top Up Amount",
        blank=True,
        null=True,
        validators=[MaxValueValidator(AUTO_TOP_UP_MAX_AMT)],
    )
    stripe_customer_id = models.CharField(
        "Stripe Customer Id", blank=True, null=True, max_length=25
    )

    AUTO_STATUS = [
        ("Off", "Off"),
        ("Pending", "Pending"),
        ("On", "On"),
    ]

    stripe_auto_confirmed = models.CharField(
        "Stripe Auto Confirmed", max_length=9, choices=AUTO_STATUS, default="Off"
    )

    system_number_search = models.BooleanField(
        "Show %s number on searches" % GLOBAL_ORG, default=True
    )
    receive_sms_results = models.BooleanField("Receive SMS Results", default=False)
    receive_sms_reminders = models.BooleanField("Receive SMS Reminders", default=False)
    receive_abf_newsletter = models.BooleanField("Receive ABF Newsletter", default=True)
    receive_marketing = models.BooleanField("Receive Marketing", default=True)
    receive_monthly_masterpoints_report = models.BooleanField(
        "Receive Monthly Masterpoints Report", default=True
    )
    receive_payments_emails = models.BooleanField(
        "Receive Payments Emails", default=True
    )
    windows_scrollbar = models.BooleanField(
        "Use Perfect Scrollbar on Windows", default=False
    )
    last_activity = models.DateTimeField(blank="True", null=True)

    REQUIRED_FIELDS = [
        "system_number",
        "email",
    ]  # tells createsuperuser to ask for them

    def __str__(self):
        if self.id in (TBA_PLAYER, RBAC_EVERYONE):
            return self.first_name
        else:
            return "%s (%s: %s)" % (self.full_name, GLOBAL_ORG, self.system_number)

    @property
    def full_name(self):
        "Returns the person's full name."
        return "%s %s" % (self.first_name, self.last_name)


class TeamMate(models.Model):
    """ link two members together """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="team_mate_user"
    )
    team_mate = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="team_mate_team_mate"
    )
    make_payments = models.BooleanField("Use my account", default=False)
