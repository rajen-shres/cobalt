"""
Data conversion script to populate BatchId fields added in sprint-48.

Script can be executed multiple times safely. On any given run it will
only try to update rows with type of UNKNOWN and state of in progress.

Once it has processed a row it will mark it as complete.
"""

import math

from django.core.management.base import BaseCommand
from django.db import transaction

from events.models import CongressMaster
from notifications.models import BatchID, EmailBatchRBAC, Snooper, BatchActivity
from organisations.models import Organisation
from post_office.models import Email as PostOfficeEmail


class Command(BaseCommand):
    def update_batch(self, batch_id_id):
        """Update a single batch - in progress and batch_type UNKNOWN"""

        with transaction.atomic():
            # Perform the databse updates as a single LUW

            try:
                batch = BatchID.objects.get(pk=batch_id_id)
            except BatchID.DoesNotExist:
                self.stdout.write(f"ERROR - can't get BatchID (id={batch_id_id})")
                self.error_count += 1
                transaction.set_rollback(True)
                return

            # Check that the batch still meets the criteria, should not happen unless
            # some other process is concurrently updating the database
            if (
                batch.batch_type != BatchID.BATCH_TYPE_UNKNOWN
                or batch.STATE != BatchID.BATCH_STATE_WIP
            ):
                self.skipped_count += 1
                return

            rbac = batch.emailbatchrbac_set.first()
            if rbac:

                # use the RBAC role to set the batch type

                if rbac.rbac_role.startswith("events.org"):
                    # treat all congress and event batches as multis
                    # don't know what activity was targetted
                    role_components = rbac.rbac_role.split(".")
                    batch.batch_type = BatchID.BATCH_TYPE_MULTI
                    # emailBatchRBAC does not have org populated for these so get from the role
                    try:
                        org = Organisation.objects.get(pk=int(role_components[2]))
                        batch.organisation = org
                    except Organisation.DoesNotExit:
                        self.stdout.write(
                            f"ERROR - can't get organisation '{role_components[2]}' from RBAC role (batch id={batch_id_id})"
                        )
                        self.error_count += 1
                        transaction.set_rollback(True)
                        return

                elif rbac.rbac_role.startswith("notifications.orgcomms"):
                    batch.organisation = rbac.meta_organisation
                    batch.batch_type = BatchID.BATCH_TYPE_COMMS

                elif rbac.rbac_role.startswith("notifications.member_comms"):
                    batch.organisation = rbac.meta_organisation
                    batch.batch_type = BatchID.BATCH_TYPE_MEMBER
            else:
                self.stdout.write(
                    f"ERROR - no EmailBatchRBAC record for BatchId id {batch_id_id}"
                )
                self.error_count += 1
                transaction.set_rollback(True)
                return

            snooper = batch.snooper_set.first()
            if snooper:
                batch.batch_size = batch.snooper_set.count()
                batch.created = snooper.post_office_email.created
                batch.description = (
                    snooper.post_office_email.subject
                    if len(snooper.post_office_email.subject) > 0
                    else "No subject available"
                )
                batch.state = BatchID.BATCH_STATE_COMPLETE
            else:
                self.stdout.write(
                    f"ERROR - no Snooper records for BatchId id {batch_id_id}"
                )
                self.error_count += 1
                transaction.set_rollback(True)
                return

            batch.save()
            self.update_count += 1

    def handle(self, *args, **options):
        self.stdout.write("Executing populate_batch_id")

        self.update_count = 0
        self.skipped_count = 0
        self.error_count = 0

        # get a list of candidate batch id keys
        batch_id_ids = list(
            BatchID.objects.filter(
                batch_type=BatchID.BATCH_TYPE_UNKNOWN, state=BatchID.BATCH_STATE_WIP
            ).values_list("id", flat=True)
        )

        candidate_count = len(batch_id_ids)
        self.stdout.write(f"{candidate_count} candidate batches found")

        report_interval = math.floor(candidate_count / 100)
        next_report_at = report_interval
        # process each key individually (as a separate transaction)
        for i, batch_id_id in enumerate(batch_id_ids):
            self.update_batch(batch_id_id)
            if i >= next_report_at:
                self.stdout.write(f"{i+1} or {candidate_count} processed")
                next_report_at += report_interval

        self.stdout.write(
            f"populate_batch_id complete - {self.update_count} updated, {self.skipped_count} skipped"
        )
