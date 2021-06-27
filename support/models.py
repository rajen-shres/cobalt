from django.db import models
from django.utils import timezone

from accounts.models import User

INCIDENT_STATUS_TYPES = [
    ("Unassigned", "Unassigned to anyone"),
    ("In Progress", "In Progress and assigned to someone"),
    ("Pending User Feedback", "Awaiting feedback from user"),
    ("Closed", "Closed"),
]
INCIDENT_NATURE_TYPES = [
    ("Security", "Security Problem"),
    ("Congress Entry", "Congress Entry Problem"),
    ("Other", "Other"),
]


class Incident(models.Model):
    """
    Something that happened and needs to be tracked. Often reported by a user.
    """

    reported_by_user = models.ForeignKey(
        User, on_delete=models.CASCADE, blank=True, null=True
    )
    """ Standard User object """

    reported_by_email = models.TextField(blank=True, null=True)
    """ for use when we do not have a user object """

    description = models.TextField()
    """ free format description """

    status = models.CharField(
        max_length=30, choices=INCIDENT_STATUS_TYPES, default="Unassigned"
    )
    """ status of this case """

    incident_type = models.CharField(
        max_length=30, choices=INCIDENT_NATURE_TYPES, default="Other"
    )
    """ type for this incident """

    created_date = models.DateTimeField("Created Date", default=timezone.now)
    """ date created """

    closed_date = models.DateTimeField("Closed Date", blank=True, null=True)
    """ date closed """

    def save(self, *args, **kwargs):
        """ handle an update """

        super().save(*args, **kwargs)

        # Notify folks
        print("Busy")


#
# class IncidentLineItem(models.Model):
#     """ a thing that happens to an Incident """
