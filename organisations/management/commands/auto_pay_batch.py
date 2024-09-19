"""
Batch command to auto pay membership fees as at today's date
"""

import logging

from django.db import transaction
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.template.loader import render_to_string

from cobalt.settings import (
    BRIDGE_CREDITS,
    GLOBAL_TITLE,
    GLOBAL_ORG,
)
from organisations.club_admin_core import (
    get_auto_pay_memberships_for_club,
    get_clubs_with_auto_pay_memberships,
    _process_membership_payment,
)
from organisations.models import (
    MemberClubDetails,
)
from notifications.models import (
    BatchID,
)
from notifications.views.core import (
    create_rbac_batch_id,
    send_cobalt_email_with_template,
)
from payments.models import (
    OrgPaymentMethod,
)
from rbac.core import (
    rbac_get_users_with_role,
)


logger = logging.getLogger("cobalt")
today = timezone.now().date()


class Command(BaseCommand):
    help = "Batch command to auto pay membership fees as at today's date"

    def notify_club(
        self,
        club,
        total_collected,
        paid_memberships,
        failed_memberships,
    ):
        """Send an email to the club notifying them of the results"""

        member_editors = rbac_get_users_with_role(f"orgs.members.{club.id}.edit")

        if not member_editors:
            logger.warning(
                f"Unable to send email to club {club}, no member editors found"
            )
            return

        email_body = render_to_string(
            "organisations/club_menu/members/auto_pay_club_email_content.html",
            {
                "club": club,
                "total_collected": total_collected,
                "paid_memberships": paid_memberships,
                "failed_memberships": failed_memberships,
                "today": today,
                "GLOBAL_TITLE": GLOBAL_TITLE,
                "BRIDGE_CREDITS": BRIDGE_CREDITS,
                "GLOBAL_ORG": GLOBAL_ORG,
            },
        )

        context = {
            "title": f"Membership auto pay transactions for {club.name}",
            "email_body": email_body,
            "box_colour": "#007bff",
        }

        # create batch ID
        batch_id = create_rbac_batch_id(
            rbac_role=f"notifications.orgcomms.{club.id}.edit",
            organisation=club,
            batch_type=BatchID.BATCH_TYPE_COMMS,
            batch_size=len(member_editors),
            description=context["title"],
            complete=True,
        )

        for user in member_editors:

            context["name"] = user.first_name

            send_cobalt_email_with_template(
                to_address=user.email,
                batch_id=batch_id,
                context=context,
            )

    def notify_member(self, club, membership, batch_id):

        email_body = render_to_string(
            "organisations/club_menu/members/auto_pay_member_email_content.html",
            {
                "club": club,
                "membership": membership,
                "today": today,
                "GLOBAL_TITLE": GLOBAL_TITLE,
                "BRIDGE_CREDITS": BRIDGE_CREDITS,
                "GLOBAL_ORG": GLOBAL_ORG,
            },
        )

        context = {
            "title": f"Membership fee payment for {club.name}",
            "name": membership.user.first_name,
            "email_body": email_body,
            "box_colour": "#007bff",
        }

        send_cobalt_email_with_template(
            to_address=membership.user.email,
            batch_id=batch_id,
            context=context,
        )

    def handle(self, *args, **options):

        logger.info("Batch auto pay starting")

        # process club by club
        clubs = get_clubs_with_auto_pay_memberships()

        logger.info(f"Batch auto pay found {len(clubs)} clubs with candidate payments")

        for club in clubs:

            logger.info(f"Batch auto pay starting {club.name}")

            memberships = get_auto_pay_memberships_for_club(club)
            if not memberships:
                continue

            # get the bridge credit paymnet method for the club (if any)
            club_bc_payment_method = OrgPaymentMethod.objects.filter(
                organisation=club,
                payment_method="Bridge Credits",
                active=True,
            ).last()

            if not club_bc_payment_method:
                logger.info(f"No allowed auto pay payments for {club.name}")
                continue

            # attempt the payments

            paid_memberships = []
            failed_memberships = []
            total_collected = 0

            # create batch ID for member notifications
            member_batch_id = create_rbac_batch_id(
                rbac_role=f"notifications.orgcomms.{club.id}.edit",
                organisation=club,
                batch_type=BatchID.BATCH_TYPE_COMMS,
                description=f"Membership fee payment for {club.name}",
                complete=False,
            )

            for membership in memberships:

                with transaction.atomic():

                    success, message = _process_membership_payment(
                        club,
                        True,
                        membership,
                        club_bc_payment_method,
                        f"{club.name} club membership (auto pay)",
                    )

                    if success:
                        membership.save()

                        if membership.member_details.latest_membership == membership:
                            # need to update the status on the member details

                            membership.member_details.membership_status = (
                                MemberClubDetails.MEMBERSHIP_STATUS_CURRENT
                            )
                            membership.member_details.save()

                        paid_memberships.append(membership)
                        total_collected += membership.fee
                        self.notify_member(club, membership, member_batch_id)

                    else:
                        logger.warning(
                            f"Auto pay failed for {membership.user.system_number} '{message}'"
                        )
                        membership.message = message
                        failed_memberships.append(membership)

            # update the members batch
            member_batch_id.batch_size = len(paid_memberships)
            member_batch_id.state = BatchID.BATCH_STATE_COMPLETE
            member_batch_id.save()

            self.notify_club(
                club, total_collected, paid_memberships, failed_memberships
            )

            logger.info(
                (
                    f"{club.name} collected {total_collected} Bridge Credits from auto pay, "
                    + f"{len(paid_memberships)} succeeded, {len(failed_memberships)} failed"
                )
            )

        logger.info("Batch auto pay finished")
