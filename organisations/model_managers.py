from django.db import models
from django.db.models import Q
from django.utils import timezone


class MemberMembershipTypeManager(models.Manager):
    """Model Manager for Memberships. Creates a filter for active membership"""

    def active(self):
        now = timezone.now()
        return self.filter(start_date__lte=now).filter(
            Q(end_date__gte=now) | Q(end_date=None)
        )
