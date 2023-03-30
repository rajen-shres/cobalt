""" Models for our definitions of a user within the system. """
import random
import string
from datetime import date

from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from cobalt.settings import (
    AUTO_TOP_UP_MAX_AMT,
    GLOBAL_ORG,
    TBA_PLAYER,
    RBAC_EVERYONE,
    ABF_USER,
    API_KEY_PREFIX,
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
        #  regex=r"^\+?1?\d{9,15}$",
        regex=r"^04\d{8}$",
        message="We only accept Australian phone numbers starting 04 which are 10 numbers long.",
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
    receive_sms_results = models.BooleanField("Receive SMS Results", default=True)
    receive_email_results = models.BooleanField(
        "Receive Results by Email", default=True
    )
    receive_sms_reminders = models.BooleanField("Receive SMS Reminders", default=False)
    receive_abf_newsletter = models.BooleanField("Receive ABF Newsletter", default=True)
    receive_marketing = models.BooleanField("Receive Marketing", default=True)
    receive_monthly_masterpoints_report = models.BooleanField(
        "Receive Monthly Masterpoints Report", default=True
    )
    receive_payments_emails = models.BooleanField(
        "Receive Payments Emails", default=True
    )
    receive_low_balance_emails = models.BooleanField(default=True)
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
    identifier = models.CharField(
        max_length=10,
        default="NOTSET",
    )
    """ random string identifier to use in emails to handle preferences. Can't use the pk obviously """

    def save(self, *args, **kwargs):
        """create identifier on first save"""
        if not self.pk:
            self.identifier = "".join(
                random.SystemRandom().choice(string.ascii_letters + string.digits)
                for _ in range(10)
            )
        super(UnregisteredUser, self).save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} ({GLOBAL_ORG}: {self.system_number})"

    @property
    def full_name(self):
        """Returns the person's full name."""
        return f"{self.first_name} {self.last_name}"


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


def _create_api_token():
    string_size = 40 - len(API_KEY_PREFIX)
    random_string = "".join(
        random.SystemRandom().choice(
            string.ascii_letters + string.digits + "!$^()-_{}|/"
        )
        for _ in range(string_size)
    )
    return f"{API_KEY_PREFIX}{random_string}"


class APIToken(models.Model):
    """API Tokens map to a user and are used by any API functions

    We don't put an expiry on the token but this could be added later if required."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.CharField(
        max_length=40,
        default="Overridden on save",
        help_text="This is set when you first save it",
    )
    created_date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} - {self.created_date}"

    def save(self, *args, **kwargs):
        """Create token on first save"""

        if len(self.token) != 40:
            self.token = _create_api_token()

        super(APIToken, self).save(*args, **kwargs)


class UserAdditionalInfo(models.Model):
    """Additional information about a user that is not regularly accessed.
    The intention is to move all of the extras from the User class into here over time
    as the User is getting overloaded and is accessed constantly by Django so we should
    try to keep it clean.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    email_hard_bounce = models.BooleanField(default=False)
    """ Set this flag if we get a hard bounce from sending an email """
    email_hard_bounce_reason = models.TextField(null=True, blank=True)
    """ Reason for the bounce """
    email_hard_bounce_date = models.DateTimeField(null=True, blank=True)
    congress_view_filters = models.CharField(max_length=200, blank=True)
    """ user preferences for the congress listing page """

    def __str__(self):
        return self.user.__str__()


class SystemCard(models.Model):
    """System cards for users"""

    class SystemClassification(models.TextChoices):
        GREEN = "G"
        BLUE = "B"
        YELLOW = "Y"
        RED = "R"

    # Meta data
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    card_name = models.CharField(max_length=100)
    save_date = models.DateTimeField(auto_now=True)

    # Basic Info
    player1 = models.CharField(max_length=100, blank=True)
    player2 = models.CharField(max_length=100, blank=True)
    basic_system = models.CharField(max_length=50, default="Standard American")
    system_classification = models.CharField(
        max_length=1,
        choices=SystemClassification.choices,
        default=SystemClassification.GREEN,
    )
    brown_sticker = models.BooleanField(default=False)
    brown_sticker_why = models.CharField(max_length=50, blank=True)
    canape = models.BooleanField(default=False)

    # Openings
    opening_1c = models.CharField(max_length=20, blank=True)
    opening_1d = models.CharField(max_length=20, blank=True)
    opening_1h = models.CharField(max_length=20, blank=True)
    opening_1s = models.CharField(max_length=20, blank=True)
    opening_1nt = models.CharField(max_length=20, blank=True)

    # Summary
    summary_bidding = models.CharField(max_length=100, blank=True)
    summary_carding = models.CharField(max_length=100, blank=True)

    # Pre-alerts
    pre_alerts = models.TextField(blank=True)

    # 1NT Responses
    nt1_response_2c = models.CharField(max_length=20, blank=True)
    nt1_response_2d = models.CharField(max_length=20, blank=True)
    nt1_response_2h = models.CharField(max_length=20, blank=True)
    nt1_response_2s = models.CharField(max_length=20, blank=True)
    nt1_response_2nt = models.CharField(max_length=20, blank=True)

    # 2 Level Openings
    opening_2c = models.CharField(max_length=20, blank=True)
    opening_2d = models.CharField(max_length=20, blank=True)
    opening_2h = models.CharField(max_length=20, blank=True)
    opening_2s = models.CharField(max_length=20, blank=True)
    opening_2nt = models.CharField(max_length=20, blank=True)

    # Higher Openings
    opening_3nt = models.CharField(max_length=20, blank=True)
    opening_other = models.CharField(max_length=20, blank=True)

    # Competitive bids
    competitive_doubles = models.CharField(max_length=100, blank=True)
    competitive_lead_directing_doubles = models.CharField(max_length=100, blank=True)
    competitive_jump_overcalls = models.CharField(max_length=100, blank=True)
    competitive_unusual_nt = models.CharField(max_length=100, blank=True)
    competitive_1nt_overcall_immediate = models.CharField(max_length=20, blank=True)
    competitive_1nt_overcall_reopening = models.CharField(max_length=20, blank=True)
    competitive_negative_double_through = models.CharField(max_length=20, blank=True)
    competitive_responsive_double_through = models.CharField(max_length=20, blank=True)
    competitive_immediate_cue_bid_minor = models.CharField(max_length=100, blank=True)
    competitive_immediate_cue_bid_major = models.CharField(max_length=100, blank=True)
    competitive_weak_2_defense = models.CharField(max_length=100, blank=True)
    competitive_weak_3_defense = models.CharField(max_length=100, blank=True)
    competitive_transfer_defense = models.CharField(max_length=100, blank=True)
    competitive_nt_defense = models.CharField(max_length=100, blank=True)

    # Basic Responses
    basic_response_jump_raise_minor = models.CharField(max_length=100, blank=True)
    basic_response_jump_raise_major = models.CharField(max_length=100, blank=True)
    basic_response_jump_shift_minor = models.CharField(max_length=100, blank=True)
    basic_response_jump_shift_major = models.CharField(max_length=100, blank=True)
    basic_response_to_2c_opening = models.CharField(max_length=100, blank=True)
    basic_response_to_strong_2_opening = models.CharField(max_length=100, blank=True)
    basic_response_to_2nt_opening = models.CharField(max_length=100, blank=True)

    # Carding - suit
    play_suit_lead_sequence = models.CharField(max_length=100, blank=True)
    play_suit_lead_4_or_more = models.CharField(max_length=100, blank=True)
    play_suit_lead_4_small = models.CharField(max_length=100, blank=True)
    play_suit_lead_3 = models.CharField(max_length=100, blank=True)
    play_suit_lead_in_partners_suit = models.CharField(max_length=100, blank=True)
    play_suit_discards = models.CharField(max_length=100, blank=True)
    play_suit_count = models.CharField(max_length=100, blank=True)
    play_suit_signal_on_partner_lead = models.CharField(max_length=100, blank=True)

    # Carding - NT
    play_nt_lead_sequence = models.CharField(max_length=100, blank=True)
    play_nt_lead_4_or_more = models.CharField(max_length=100, blank=True)
    play_nt_lead_4_small = models.CharField(max_length=100, blank=True)
    play_nt_lead_3 = models.CharField(max_length=100, blank=True)
    play_nt_lead_in_partners_suit = models.CharField(max_length=100, blank=True)
    play_nt_discards = models.CharField(max_length=100, blank=True)
    play_nt_count = models.CharField(max_length=100, blank=True)
    play_nt_signal_on_partner_lead = models.CharField(max_length=100, blank=True)

    play_signal_declarer_lead = models.CharField(max_length=100, blank=True)
    play_notes = models.CharField(max_length=100, blank=True)

    # Slams
    slam_conventions = models.CharField(max_length=200, blank=True)

    # Other
    other_conventions = models.CharField(max_length=200, blank=True)

    # Responses
    # 1C
    response_1c_1d = models.CharField(max_length=20, blank=True)
    response_1c_1h = models.CharField(max_length=20, blank=True)
    response_1c_1s = models.CharField(max_length=20, blank=True)
    response_1c_1n = models.CharField(max_length=20, blank=True)
    response_1c_2c = models.CharField(max_length=20, blank=True)
    response_1c_2d = models.CharField(max_length=20, blank=True)
    response_1c_2h = models.CharField(max_length=20, blank=True)
    response_1c_2s = models.CharField(max_length=20, blank=True)
    response_1c_2n = models.CharField(max_length=20, blank=True)
    response_1c_3c = models.CharField(max_length=20, blank=True)
    response_1c_3d = models.CharField(max_length=20, blank=True)
    response_1c_3h = models.CharField(max_length=20, blank=True)
    response_1c_3s = models.CharField(max_length=20, blank=True)
    response_1c_3n = models.CharField(max_length=20, blank=True)
    response_1c_other = models.CharField(max_length=100, blank=True)

    # 1D
    response_1d_1h = models.CharField(max_length=20, blank=True)
    response_1d_1s = models.CharField(max_length=20, blank=True)
    response_1d_1n = models.CharField(max_length=20, blank=True)
    response_1d_2c = models.CharField(max_length=20, blank=True)
    response_1d_2d = models.CharField(max_length=20, blank=True)
    response_1d_2h = models.CharField(max_length=20, blank=True)
    response_1d_2s = models.CharField(max_length=20, blank=True)
    response_1d_2n = models.CharField(max_length=20, blank=True)
    response_1d_3c = models.CharField(max_length=20, blank=True)
    response_1d_3d = models.CharField(max_length=20, blank=True)
    response_1d_3h = models.CharField(max_length=20, blank=True)
    response_1d_3s = models.CharField(max_length=20, blank=True)
    response_1d_3n = models.CharField(max_length=20, blank=True)
    response_1d_other = models.CharField(max_length=100, blank=True)

    # 1H
    response_1h_1s = models.CharField(max_length=20, blank=True)
    response_1h_1n = models.CharField(max_length=20, blank=True)
    response_1h_2c = models.CharField(max_length=20, blank=True)
    response_1h_2d = models.CharField(max_length=20, blank=True)
    response_1h_2h = models.CharField(max_length=20, blank=True)
    response_1h_2s = models.CharField(max_length=20, blank=True)
    response_1h_2n = models.CharField(max_length=20, blank=True)
    response_1h_3c = models.CharField(max_length=20, blank=True)
    response_1h_3d = models.CharField(max_length=20, blank=True)
    response_1h_3h = models.CharField(max_length=20, blank=True)
    response_1h_3s = models.CharField(max_length=20, blank=True)
    response_1h_3n = models.CharField(max_length=20, blank=True)
    response_1h_other = models.CharField(max_length=100, blank=True)

    # 1S
    response_1s_1n = models.CharField(max_length=20, blank=True)
    response_1s_2c = models.CharField(max_length=20, blank=True)
    response_1s_2d = models.CharField(max_length=20, blank=True)
    response_1s_2h = models.CharField(max_length=20, blank=True)
    response_1s_2s = models.CharField(max_length=20, blank=True)
    response_1s_2n = models.CharField(max_length=20, blank=True)
    response_1s_3c = models.CharField(max_length=20, blank=True)
    response_1s_3d = models.CharField(max_length=20, blank=True)
    response_1s_3h = models.CharField(max_length=20, blank=True)
    response_1s_3s = models.CharField(max_length=20, blank=True)
    response_1s_3n = models.CharField(max_length=20, blank=True)
    response_1s_other = models.CharField(max_length=100, blank=True)

    # 1N
    response_1n_3c = models.CharField(max_length=20, blank=True)
    response_1n_3d = models.CharField(max_length=20, blank=True)
    response_1n_3h = models.CharField(max_length=20, blank=True)
    response_1n_3s = models.CharField(max_length=20, blank=True)
    response_1n_3n = models.CharField(max_length=20, blank=True)
    response_1n_other = models.CharField(max_length=100, blank=True)

    # 2c
    response_2c_2d = models.CharField(max_length=20, blank=True)
    response_2c_2h = models.CharField(max_length=20, blank=True)
    response_2c_2s = models.CharField(max_length=20, blank=True)
    response_2c_2n = models.CharField(max_length=20, blank=True)
    response_2c_3c = models.CharField(max_length=20, blank=True)
    response_2c_3d = models.CharField(max_length=20, blank=True)
    response_2c_3h = models.CharField(max_length=20, blank=True)
    response_2c_3s = models.CharField(max_length=20, blank=True)
    response_2c_3n = models.CharField(max_length=20, blank=True)
    response_2c_other = models.CharField(max_length=100, blank=True)

    # 2d
    response_2d_2h = models.CharField(max_length=20, blank=True)
    response_2d_2s = models.CharField(max_length=20, blank=True)
    response_2d_2n = models.CharField(max_length=20, blank=True)
    response_2d_3c = models.CharField(max_length=20, blank=True)
    response_2d_3d = models.CharField(max_length=20, blank=True)
    response_2d_3h = models.CharField(max_length=20, blank=True)
    response_2d_3s = models.CharField(max_length=20, blank=True)
    response_2d_3n = models.CharField(max_length=20, blank=True)
    response_2d_other = models.CharField(max_length=100, blank=True)

    # 2h
    response_2h_2s = models.CharField(max_length=20, blank=True)
    response_2h_2n = models.CharField(max_length=20, blank=True)
    response_2h_3c = models.CharField(max_length=20, blank=True)
    response_2h_3d = models.CharField(max_length=20, blank=True)
    response_2h_3h = models.CharField(max_length=20, blank=True)
    response_2h_3s = models.CharField(max_length=20, blank=True)
    response_2h_3n = models.CharField(max_length=20, blank=True)
    response_2h_other = models.CharField(max_length=100, blank=True)

    # 2s
    response_2s_2n = models.CharField(max_length=20, blank=True)
    response_2s_3c = models.CharField(max_length=20, blank=True)
    response_2s_3d = models.CharField(max_length=20, blank=True)
    response_2s_3h = models.CharField(max_length=20, blank=True)
    response_2s_3s = models.CharField(max_length=20, blank=True)
    response_2s_3n = models.CharField(max_length=20, blank=True)
    response_2s_other = models.CharField(max_length=100, blank=True)

    # 2NT
    response_2n_3c = models.CharField(max_length=20, blank=True)
    response_2n_3d = models.CharField(max_length=20, blank=True)
    response_2n_3h = models.CharField(max_length=20, blank=True)
    response_2n_3s = models.CharField(max_length=20, blank=True)
    response_2n_3n = models.CharField(max_length=20, blank=True)
    response_2n_other = models.CharField(max_length=100, blank=True)

    # notes
    response_notes = models.CharField(max_length=200, blank=True)

    other_notes = models.CharField(max_length=400, blank=True)

    def __str__(self):
        local_datetime = timezone.localtime(self.save_date)
        return f"{self.user.full_name} - {self.card_name} - {local_datetime:%a %-d %b %Y %I:%M%p}"
