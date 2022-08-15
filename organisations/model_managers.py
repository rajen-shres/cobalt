from django.db import models
from django.db.models import Q
from django.utils import timezone


# TODO: This isn't working and needs to be investigated properly.
# For now we don't call it and will probably change this to have an archive table for historic membership viewing


class MemberMembershipTypeManager(models.Manager):
    """Model Manager for Memberships. Creates a filter for active membership"""

    def active(self, ref_date=timezone.now()):

        return self.filter(start_date__lte=ref_date).filter(
            Q(end_date__gte=ref_date) | Q(end_date=None)
        )
