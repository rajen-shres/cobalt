from django.db import models
from django.utils import timezone

from accounts.models import User

INCIDENT_STATUS_TYPES = [
    ("Unassigned", "Unassigned"),
    ("In Progress", "In Progress"),
    ("Pending User Feedback", "Awaiting User Feedback"),
    ("Closed", "Closed"),
]
INCIDENT_NATURE_TYPES = [
    ("Security", "Security Problem"),
    ("Congress Entry", "Congress Entry Problem"),
    ("Other", "Other"),
]
INCIDENT_COMMENT_TYPE = [
    ("Normal", "Normal - seen by all"),
    ("Private", "Private - not shown to user"),
]
INCIDENT_SEVERITY = [
    ("Low", "Low"),
    ("Medium", "Medium"),
    ("High", "High"),
    ("Critical", "Critical"),
]


class Incident(models.Model):
    """
    Something that happened and needs to be tracked. Often reported by a user.
    """

    reported_by_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="reporter",
    )
    """ Standard User object - who reported it"""

    assigned_to = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="assignee",
    )
    """ Standard User object - who is working on it"""

    reported_by_email = models.CharField(max_length=100, blank=True, null=True)
    """ for use when we do not have a user object """

    title = models.CharField(max_length=80)
    """ Short description """

    description = models.TextField()
    """ free format description """

    status = models.CharField(
        max_length=30, choices=INCIDENT_STATUS_TYPES, default="Unassigned"
    )
    """ status of this case """

    severity = models.CharField(
        max_length=10, choices=INCIDENT_SEVERITY, default="Medium"
    )
    """ severity of this case """

    incident_type = models.CharField(
        max_length=30, choices=INCIDENT_NATURE_TYPES, default="Other"
    )
    """ type for this incident """

    created_date = models.DateTimeField("Created Date", default=timezone.now)
    """ date created """

    closed_date = models.DateTimeField("Closed Date", blank=True, null=True)
    """ date closed """

    def __str__(self):
        return f"{self.incident_type} - {self.reported_by_user}"


class IncidentLineItem(models.Model):
    """ a thing that happens to an Incident """

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE)
    """ Parent incident """

    staff = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    """ Standard User object """

    comment_type = models.CharField(
        max_length=7, choices=INCIDENT_COMMENT_TYPE, default="Normal"
    )
    """ Public or private comment """

    description = models.TextField()
    """ free format description """

    created_date = models.DateTimeField("Created Date", default=timezone.now)
    """ date created """

    def __str__(self):
        return f"{self.incident} - {self.staff}"

    # def save(self, *args, **kwargs):
    #     """ handle an update """
    #
    #     super().save(*args, **kwargs)
    #
    #     # Notify folks
    #     print("Busy")
