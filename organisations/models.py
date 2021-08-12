from django.db import models
from django.conf import settings
from accounts.models import User
from django.utils import timezone
from django.core.validators import RegexValidator

# Variable to control what is expected to be in the RBAC structure for Organisations
# A management script runs to update RBAC structure for all clubs if a new option is found.

ORGS_RBAC_GROUPS_AND_ROLES = {
    # Conveners for this orgs events
    # CONVENERS IS THE ANCHOR. THIS IS ASSUMED TO BE THERE WHEN TESTING FOR ADVANCED RBAC.
    # DO NOT CHANGE WITHOUT CHANGING IN CODE
    "conveners": {
        "app": "events",
        "model": "org",
        "action": "edit",
        "description": "Manage congresses",
    },
    # See payments details
    "payments_view": {
        "app": "payments",
        "model": "manage",
        "action": "view",
        "description": "View payments info",
    },
    # Change payments details
    "payments_edit": {
        "app": "payments",
        "model": "manage",
        "action": "edit",
        "description": "Edit payments info",
    },
}


class Organisation(models.Model):
    """Many of these fields map to fields in the Masterpoints Database
    We don't worry about phone numbers and addresses for secretaries and MP secretaries
    They seem to relate to sending letters to people. We keep the Venue address though."""

    bsb_regex = RegexValidator(
        regex=r"^\d{6}$",
        message="BSB must be exactly 6 numbers long.",
    )

    account_regex = RegexValidator(
        regex=r"^[0-9-]*$",
        message="Account number must contain only digits and dashes",
    )

    ORG_TYPE = [
        ("Club", "Bridge Club"),
        ("State", "State Association"),
        ("National", "National Body"),
        ("Other", "Other"),
    ]

    ORG_STATUS = [
        ("Open", "Open"),
        ("Closed", "Closed"),
    ]

    org_id = models.CharField(max_length=4, unique=True)
    """ maps to MPC OrgID """

    status = models.CharField(choices=ORG_STATUS, max_length=6, default="Open")

    name = models.CharField(max_length=50)
    """ maps to MPC ClubName """

    secretary = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="secretary"
    )
    """ maps to MPC ClubSecName, but we need to map this to a Cobalt user so not a CharField """

    type = models.CharField(choices=ORG_TYPE, max_length=8, blank=True, null=True)

    club_email = models.CharField(max_length=40, blank=True, null=True)
    """ maps to PMC ClubEmail """

    address1 = models.CharField("Address Line 1", max_length=100, blank=True, null=True)
    """ maps to MPC VenueAddress1 """

    address2 = models.CharField("Address Line 2", max_length=100, blank=True, null=True)
    """ maps to MPC VenueAddress2 """

    suburb = models.CharField(max_length=50, blank=True, null=True)
    """ maps to MPC Venue suburb """

    state = models.CharField(max_length=3, blank=True, null=True)
    """ maps to MPC VenueState"""

    postcode = models.CharField(max_length=10, blank=True, null=True)
    """ maps to MPC VenuePostcode """

    club_website = models.CharField(max_length=100, blank=True, null=True)
    """ maps to MPC ClubWebsite """

    bank_bsb = models.CharField(
        "BSB Number", max_length=7, blank=True, null=True, validators=[bsb_regex]
    )
    bank_account = models.CharField(
        "Bank Account Number",
        max_length=14,
        blank=True,
        null=True,
        validators=[account_regex],
    )
    membership_renewal_date = models.DateField(
        "Membership Renewal Date", blank=True, null=True
    )

    membership_part_year_date = models.DateField(
        "Membership Part Year Date", blank=True, null=True
    )
    """After this date membership discounts for the rest of the year apply"""

    last_updated_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="org_last_updated_by",
    )
    last_updated = models.DateTimeField(auto_now=True)

    @property
    def settlement_fee_percent(self):
        """return what our settlement fee is set to"""

        import payments.models as payments

        # Check for specific setting for this org
        override = payments.OrganisationSettlementFees.objects.filter(
            organisation=self
        ).first()
        if override:
            return override.org_fee_percent

        # return default
        default = payments.PaymentStatic.objects.filter(active=True).last()

        return default.default_org_fee_percent

    @property
    def rbac_name_qualifier(self):
        """We use the rbac name qualifier a lot for clubs. Neater to have as a property

        This shows where in the RBAC tree this club lives.

        """

        return "rbac.orgs.clubs.generated.%s.%s" % (
            self.state.lower(),
            self.id,
        )

    @property
    def rbac_admin_name_qualifier(self):
        """
        This shows where in the RBAC admin tree this club lives.
        """

        return "admin.clubs.generated.%s.%s" % (
            self.state.lower(),
            self.id,
        )

    def __str__(self):
        return self.name


class MembershipType(models.Model):
    """Clubs can have multiple membership types. A member can only belong to one membership type per club"""

    organisation = models.ForeignKey(Organisation, on_delete=models.PROTECT)
    name = models.CharField("Type of Membership", max_length=20)
    description = models.TextField(
        "Description of Membership Type", blank=True, null=True
    )
    annual_fee = models.DecimalField("Annual Fee", max_digits=12, decimal_places=2)
    part_year_fee = models.DecimalField(
        "Part Year Fee", max_digits=12, decimal_places=2, blank=True, null=True
    )
    does_not_pay_session_fees = models.BooleanField(
        "Does Not Pay Session Fees", default=False
    )
    does_not_renew = models.BooleanField("Does Not Renew", default=False)
    last_modified_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.organisation} - {self.name}"


class MemberMembershipType(models.Model):
    """This links members to a club membership"""

    TERMINATION_REASON = [
        ("Cancelled by Member", "Cancelled by Member"),
        ("Cancelled by Club", "Cancelled by Club"),
        ("Expired", "Expired"),
    ]

    member = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="membership_member"
    )
    membership_type = models.ForeignKey(MembershipType, on_delete=models.PROTECT)
    termination_reason = models.CharField(
        "Reason for Membership Termination",
        choices=TERMINATION_REASON,
        max_length=20,
        blank=True,
        null=True,
    )
    home_club = models.BooleanField("Is Member's Home Club", default=False)
    start_date = models.DateField("Started At", auto_now_add=True)
    end_date = models.DateField("Ends At", blank=True, null=True)
    last_modified_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="last_modified_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def active(self):
        """Get if this is active or not"""
        now = timezone.now()
        if self.start_date > now:
            return False
        if self.end_date < now:
            return False
        return True

    def __str__(self):
        return f"{self.member.full_name}, member of {self.membership_type.organisation.name}"


class ClubLog(models.Model):
    """log of things that happen for a Club"""

    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE)
    actor = models.ForeignKey(User, on_delete=models.CASCADE)
    action_date = models.DateTimeField(auto_now_add=True)
    action = models.TextField("Action")

    def __str__(self):
        return f"{self.organisation} -  {self.actor}"
