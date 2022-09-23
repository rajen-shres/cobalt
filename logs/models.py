from django.db import models
from django.utils import timezone

from accounts.models import User


class Log(models.Model):

    # SEVERITY_CODES = [
    #     ("DEBUG", "Level 0 - Debug"),
    #     ("INFO", "Level 1 - Informational"),
    #     ("WARN", "Level 2 - Warning"),
    #     ("ERROR", "Level 3 - Error"),
    #     ("HIGH", "Level 4 - High"),
    #     ("CRITICAL", "Level 5 - Critical"),
    # ]

    class SeverityCodes(models.TextChoices):
        DEBUG = "DEBUG", "Level 0 - Debug"
        INFO = "INFO", "Level 1 - Informational"
        WARN = "WARN", "Level 2 - Warning"
        ERROR = "ERROR", "Level 3 - Error"
        HIGH = "HIGH", "Level 4 - High"
        CRITICAL = "CRITICAL", "Level 5 - Critical"

    event_date = models.DateTimeField(default=timezone.now)
    user = models.CharField(max_length=200, blank=True, null=True)
    """ User is a text field to put the name of the user. Sometimes we don't have a user for an event """
    user_object = models.ForeignKey(
        User, blank=True, null=True, on_delete=models.CASCADE
    )
    """ User object will be a real user object if we have one """
    severity = models.CharField(
        max_length=8,
        choices=SeverityCodes.choices,
        default=SeverityCodes.INFO,
        blank=True,
        null=True,
    )
    source = models.CharField(max_length=40, blank=True, null=True)
    sub_source = models.CharField(max_length=50, blank=True, null=True)
    message = models.TextField(blank=True, null=True)
    ip = models.CharField(max_length=15, blank=True, null=True)

    def __str__(self):
        return f"{self.event_date}: {self.severity}: {self.source}: {self.sub_source}: {self.user}: {self.message}"
