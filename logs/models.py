from django.db import models
from django.conf import settings
from django.utils import timezone


class Log(models.Model):

    SEVERITY_CODES = [
        ("DEBUG", "Level 0 - Debug"),
        ("INFO", "Level 1 - Informational"),
        ("WARN", "Level 2 - Warning"),
        ("ERROR", "Level 3 - Error"),
        ("HIGH", "Level 4 - High"),
        ("CRITICAL", "Level 5 - Critical"),
    ]

    event_date = models.DateTimeField(default=timezone.now)
    user = models.CharField(max_length=80, blank="True", null=True)
    severity = models.CharField(max_length=8, choices=SEVERITY_CODES, default="INFO")
    source = models.CharField(max_length=40, blank="True", null=True)
    sub_source = models.CharField(max_length=50, blank="True", null=True)
    message = models.TextField(blank="True", null=True)
    ip = models.CharField(max_length=15, blank="True", null=True)

    def __str__(self):
        return "%s: %s: %s: %s: %s: %s" % (
            self.event_date,
            self.severity,
            self.source,
            self.sub_source,
            self.user,
            self.message,
        )
