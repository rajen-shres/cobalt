import bleach
from django.db import models
from django.utils import timezone

from accounts.models import User
from cobalt.settings import (
    BLEACH_ALLOWED_ATTRIBUTES,
    BLEACH_ALLOWED_TAGS,
    BLEACH_ALLOWED_STYLES,
)

INCIDENT_STATUS_TYPES = [
    ("Unassigned", "Unassigned"),
    ("In Progress", "In Progress"),
    ("Pending User Feedback", "Awaiting User Feedback"),
    ("Closed", "Closed"),
]
INCIDENT_NATURE_TYPES = [
    ("Bridge Credits", "Bridge Credits"),
    ("Congress Admin", "Congress Admin"),
    ("Congress Entry", "Congress Entry"),
    ("Club Admin", "Club Admin"),
    ("Forums", "Forums"),
    ("Masterpoints", "Masterpoints"),
    ("Notifications", "Notifications"),
    ("Other", "Other"),
    ("Payments/Refunds", "Payments/Refunds"),
    ("Profile/Settings", "Profile/Settings"),
    ("Registration", "Registration"),
    ("Security", "Security"),
]
INCIDENT_COMMENT_TYPE = [
    ("Normal", "Normal - seen by all"),
    ("Private", "Private - not shown to user"),
]
INCIDENT_SEVERITY = [
    ("Critical", "Critical"),
    ("High", "High"),
    ("Medium", "Medium"),
    ("Low", "Low"),
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
    """ Standard User object - who reported it """

    assigned_to = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="assignee",
    )
    """ Standard User object - who is working on it"""

    reported_by_email = models.EmailField(blank=True, null=True)
    """ for use when we do not have a user object """

    reported_by_name = models.CharField(max_length=100, blank=True, null=True)
    """ for use when we do not have a user object """

    title = models.CharField("Subject", max_length=80)
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

    def save(self, *args, **kwargs):
        if self.description and getattr(self, "_description_changed", True):
            self.description = bleach.clean(
                self.description,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        super(Incident, self).save(*args, **kwargs)


class IncidentLineItem(models.Model):
    """a thing that happens to an Incident"""

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

    def save(self, *args, **kwargs):
        if self.description and getattr(self, "_description_changed", True):
            self.description = bleach.clean(
                self.description,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )
        super(IncidentLineItem, self).save(*args, **kwargs)


class Attachment(models.Model):
    """screenshots etc"""

    document = models.FileField(upload_to="helpdesk/%Y/%m/%d/")
    create_date = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE)
    description = models.CharField("Description", max_length=200)

    def __str__(self):
        return f"{self.incident} - {self.description}"


class NotifyUserByType(models.Model):
    """Which users to tell about new tickets. We add an "All" option to the incident_type. Specifying all
    means the user will receive all notifications.

    Note that this is for notifications only. In order to be a support staff member you need to be in
    the RBAC group "support.helpdesk.edit"

    This allows people to be added to notifications without giving them access to the helpdesk module.
    """

    staff = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    """ Standard User object """

    incident_type = models.CharField(
        max_length=30, choices=INCIDENT_NATURE_TYPES + [("All", "All")], default="All"
    )
    """ type for this incident """

    def __str__(self):
        return f"{self.staff.full_name} - {self.incident_type}"
