import datetime
from decimal import Decimal

from django.db import models
from django.utils import timezone

from accounts.models import User
from organisations.models import Organisation, MembershipType, OrgVenue
from payments.models import OrgPaymentMethod, OrganisationTransaction, MemberTransaction
from utils.models import Seat

DEFAULT_FEE = Decimal(5.0)


class MasterSessionType(models.TextChoices):
    """Master list of different types of session that are supported
    The idea with this is that different things will happen depending
    upon the master_session_type. Currently nothing happens so this
    is just set to DUPLICATE.
    """

    DUPLICATE = "DP", "Duplicate"
    MULTI_SESSION = "MS", "Multi-Session"
    WORKSHOP = "WS", "Workshop"


class TimeOfDay(models.TextChoices):
    """Master list of session names, may need to be changed to a list that clubs can edit"""

    AM = "AM", "Morning"
    PM = "PM", "Afternoon"
    EVENING = "EV", "Evening"
    ALL_DAY = "AL", "All Day"


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
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=DEFAULT_FEE)

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
    venue = models.ForeignKey(OrgVenue, blank=True, null=True, on_delete=models.CASCADE)
    time_of_day = models.CharField(
        max_length=2,
        choices=TimeOfDay.choices,
        default=TimeOfDay.AM,
        null=True,
    )

    def __str__(self):
        return f"{self.description} - {self.session_date}"


class SessionEntry(models.Model):
    """A player who is playing in a session"""

    session = models.ForeignKey(Session, on_delete=models.PROTECT)
    system_number = models.IntegerField()
    pair_team_number = models.IntegerField()
    seat = models.CharField(choices=Seat.choices, max_length=1, null=True, blank=True)
    seat_number_internal = models.PositiveIntegerField(null=True, blank=True)
    """ seat_number_internal is used to sort NSEW in order """
    org_tran = models.ForeignKey(
        OrganisationTransaction, on_delete=models.PROTECT, null=True, blank=True
    )
    member_tran = models.ForeignKey(
        MemberTransaction, on_delete=models.PROTECT, null=True, blank=True
    )
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.ForeignKey(
        OrgPaymentMethod, on_delete=models.PROTECT, null=True, blank=True
    )
    fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name_plural = "Session entries"
        unique_together = ("session", "pair_team_number", "seat")
        ordering = ["pair_team_number", "seat_number_internal"]

    def save(self, *args, **kwargs):
        """We add the seat number internal on save so we can load from database in order NSEW"""
        if self.seat:
            self.seat_number_internal = "NSEW".find(self.seat)
        super(SessionEntry, self).save(*args, **kwargs)

    def __str__(self):
        return f"{self.session}: {self.system_number}"
