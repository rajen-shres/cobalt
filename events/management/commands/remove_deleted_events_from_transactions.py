"""
Remove event_id references on member and organisation transactions
where the corresponding event no longer exists.

This is a one-off data clean-up for issues caused before the implementation of COB-799.
"""

from django.core.management.base import BaseCommand
from django.db.models import Subquery

from payments.models import OrganisationTransaction, MemberTransaction
from events.models import Event


class Command(BaseCommand):
    def handle(self, *args, **options):

        organisation_txns = OrganisationTransaction.objects.exclude(
            event_id=None
        ).exclude(event_id__in=Subquery(Event.objects.values("pk")))

        for organisation_txn in organisation_txns:
            print(f"Organsisation txn: {organisation_txn.event_id}")
            organisation_txn.event_id = None
            organisation_txn.save()

        member_txns = MemberTransaction.objects.exclude(event_id=None).exclude(
            event_id__in=Subquery(Event.objects.values("pk"))
        )

        for member_txn in member_txns:
            print(f"Member txn: {member_txn.event_id}")
            member_txn.event_id = None
            member_txn.save()
