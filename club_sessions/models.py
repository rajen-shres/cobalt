import datetime

from django.db import models
from django.utils import timezone

from accounts.models import User
from organisations.models import Organisation, MembershipType
from payments.models import OrgPaymentMethod, OrganisationTransaction, MemberTransaction
from utils.models import Seat


class MasterSessionType(models.TextChoices):
    """Master list of different types of session that are supported"""

    DUPLICATE = "DP", "Duplicate"
    MULTI_SESSION = "MS", "Multi-session"
    WORKSHOP = "WS", "Workshop"


class SessionType(models.Model):
    """Specific club session types"""

    name = models.CharField(max_length=15)
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE)
    master_session_type = models.CharField(
        max_length=2,
        choices=MasterSessionType.choices,
        default=MasterSessionType.DUPLICATE,
    )
    status = models.BooleanField(default=True)

    # class Meta:
    #     unique_together = ["organisation", "master_session_type"]

    def __str__(self):
        if self.status:
            return f"{self.organisation} - {self.master_session_type}"
        else:
            return f"Not Active - {self.organisation} - {self.master_session_type}"


class SessionTypePaymentMethod(models.Model):
    """Payment types for a session type"""

    session_type = models.ForeignKey(SessionType, on_delete=models.CASCADE)
    payment_method = models.ForeignKey(OrgPaymentMethod, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.session_type} - {self.payment_method.payment_method}"


class SessionTypePaymentMethodMembership(models.Model):
    """Links a session type (and payment method) to a membership type and sets the fee"""

    session_type_payment_method = models.ForeignKey(
        SessionTypePaymentMethod, on_delete=models.CASCADE
    )
    membership = models.ForeignKey(
        MembershipType, on_delete=models.CASCADE, null=True, blank=True
    )
    """ This either holds a link to a membership type or can be blank to signify the rate for non-members"""
    fee = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.membership} - {self.session_type_payment_method}"


class Session(models.Model):
    """Basic definition of a session of bridge"""

    director = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    session_type = models.ForeignKey(SessionType, on_delete=models.CASCADE)
    session_date = models.DateField(default=timezone.now)
    description = models.CharField(max_length=30)

    def __str__(self):
        return f"{self.session_type} - {self.description}"


class SessionEntry(models.Model):
    """A player who is playing in a session"""

    session = models.ForeignKey(Session, on_delete=models.PROTECT)
    player = models.ForeignKey(User, on_delete=models.PROTECT)
    pair_team_number = models.IntegerField()
    seat = models.CharField(choices=Seat.choices, max_length=1, null=True, blank=True)
    org_tran = models.ForeignKey(
        OrganisationTransaction, on_delete=models.PROTECT, null=True, blank=True
    )
    member_tran = models.ForeignKey(
        MemberTransaction, on_delete=models.PROTECT, null=True, blank=True
    )
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.ForeignKey(OrgPaymentMethod, on_delete=models.CASCADE)

    class Meta:
        verbose_name_plural = "Session entries"
