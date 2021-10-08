""" Models for our definitions of a user within the system. """

from datetime import date

from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from cobalt.settings import (
    AUTO_TOP_UP_MAX_AMT,
    GLOBAL_ORG,
    TBA_PLAYER,
    RBAC_EVERYONE,
    ABF_USER,
)
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, RegexValidator
from django.db import models


def no_future(value):
    today = date.today()
    if value > today:
        raise ValidationError("Date cannot be in the future.")


class User(AbstractUser):
    """
    User class based upon AbstractUser.
    """

    class CovidStatus(models.TextChoices):
        UNSET = "US", "Unset"
        USER_CONFIRMED = "UC", "User Confirmed"
        ADMIN_CONFIRMED = "AC", "Administrator Confirmed"
        USER_EXEMPT = "AV", "User Medically Exempt from Vaccination"

    email = models.EmailField(unique=False)
    system_number = models.IntegerField(
        "%s Number" % GLOBAL_ORG,
        blank=True,
        unique=True,
        db_index=True,
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
    dob = models.DateField(blank="True", null=True, validators=[no_future])
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

    covid_status = models.CharField(
        choices=CovidStatus.choices, max_length=2, default=CovidStatus.UNSET
    )

    REQUIRED_FIELDS = [
        "system_number",
        "email",
    ]  # tells createsuperuser to ask for them

    def __str__(self):
        if self.id in (TBA_PLAYER, RBAC_EVERYONE, ABF_USER):
            return self.first_name
        else:
            return "%s (%s: %s)" % (self.full_name, GLOBAL_ORG, self.system_number)

    @property
    def full_name(self):
        """Returns the person's full name."""
        return "%s %s" % (self.first_name, self.last_name)

    @property
    def href(self):
        """Returns an HTML link tag that can be used to go to the users public profile"""

        url = reverse("accounts:public_profile", kwargs={"pk": self.id})
        return format_html(
            "<a href='{}' target='_blank'>{}</a>", mark_safe(url), self.full_name
        )


class UnregisteredUser(models.Model):
    """Represents users who we have only partial information about and who have not registered themselves yet.
    When a User registers, the matching instance of Unregistered User will be removed.

    Email addresses are a touchy subject as some clubs believe they own this information and do not
    want it shared with other clubs. We protect email address by having another model (UnregisteredUserEmail)
    that is organisation specific. The email address in this model is from the MPC (considered "public"
    although it is not shown to anyone), while the other email address is "private" to the club that
    provided it, but ironically shown to the club that did and editable.
    """

    # Import here to avoid circular dependencies
    from organisations.models import Organisation

    ORIGINS = [
        ("MPC", "Masterpoints Centre Import"),
        ("Pianola", "Pianola Import"),
        ("CSV", "CSV Import"),
        ("Manual", "Manual Entry"),
    ]

    system_number = models.IntegerField(
        "%s Number" % GLOBAL_ORG,
        unique=True,
        db_index=True,
    )
    first_name = models.CharField("First Name", max_length=150, blank=True, null=True)
    last_name = models.CharField("Last Name", max_length=150, blank=True, null=True)
    email = models.EmailField(
        "Email Address (accessible by all clubs)", blank=True, null=True
    )
    origin = models.CharField("Origin", choices=ORIGINS, max_length=10)
    last_updated_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="last_updated"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_registration_invite_sent = models.DateTimeField(
        "Last Registration Invite Sent", blank=True, null=True
    )
    last_registration_invite_by_user = models.ForeignKey(
        User, on_delete=models.PROTECT, blank=True, null=True
    )
    last_registration_invite_by_club = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="last_registration_invite_by_club",
    )
    added_by_club = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="added_by_club",
    )

    def __str__(self):
        return "%s (%s: %s)" % (self.full_name, GLOBAL_ORG, self.system_number)

    @property
    def full_name(self):
        """Returns the person's full name."""
        return "%s %s" % (self.first_name, self.last_name)


class TeamMate(models.Model):
    """link two members together"""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="team_mate_user"
    )
    team_mate = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="team_mate_team_mate"
    )
    make_payments = models.BooleanField("Use my account", default=False)

    def __str__(self):
        if self.make_payments:
            return f"Plus - {self.user.full_name} - {self.team_mate.full_name}"
        else:
            return f"Basic - {self.user.full_name} - {self.team_mate.full_name}"


class UserPaysFor(models.Model):
    """Allow a user to charge their bridge to another person"""

    class Circumstance(models.TextChoices):
        ALWAYS = "AL", "Always"
        IF_PLAYING_TOGETHER = "PT", "If Playing Together"
        IF_PLAYING_SAME_SESSION = "PS", "If Playing Same Session"

    sponsor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sponsor")
    lucky_person = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="lucky_person"
    )
    criterion = models.CharField(
        max_length=2, choices=Circumstance.choices, default=Circumstance.ALWAYS
    )

    def __str__(self):
        return f"{self.sponsor.full_name} pays for {self.lucky_person.full_name}"
