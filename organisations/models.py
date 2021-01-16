from django.db import models
from django.conf import settings
from accounts.models import User
from django.utils import timezone
from django.core.validators import RegexValidator


class Organisation(models.Model):

    bsb_regex = RegexValidator(
        regex=r"^\d{3}-\d{3}$", message="BSB must be entered in the format: '999-999'.",
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
    org_id = models.CharField(max_length=4, unique=True)
    name = models.CharField(max_length=50)
    type = models.CharField(choices=ORG_TYPE, max_length=8, blank="True", null=True)
    address1 = models.CharField(
        "Address Line 1", max_length=100, blank="True", null=True
    )
    address2 = models.CharField(
        "Address Line 2", max_length=100, blank="True", null=True
    )
    suburb = models.CharField(max_length=50, blank="True", null=True)
    state = models.CharField(max_length=3, blank="True", null=True)
    postcode = models.CharField(max_length=10, blank="True", null=True)
    bank_bsb = models.CharField(
        "BSB Number", max_length=7, blank="True", null=True, validators=[bsb_regex]
    )
    bank_account = models.CharField(
        "Bank Account Number",
        max_length=14,
        blank="True",
        null=True,
        validators=[account_regex],
    )
    last_updated_by = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True,
    )
    last_updated = models.DateTimeField(default=timezone.now)

    @property
    def settlement_fee_percent(self):
        """ return what our settlement fee is set to """

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

    def __str__(self):
        return self.name


class MemberOrganisation(models.Model):
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE)
    home_club = models.BooleanField(blank=True, null=True)
    home_state = models.BooleanField(blank=True, null=True)

    def __str__(self):
        return f"{self.member.full_name}, member of {self.organisation.name}"
