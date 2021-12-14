from django.db import models

from accounts.models import User


class ApiLog(models.Model):
    """Logging of API usage. All API calls should create a record here"""

    api = models.CharField(max_length=300)
    version = models.CharField(max_length=10)
    admin = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    created_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.api} - {self.version} - {self.admin} - {self.created_date}"
