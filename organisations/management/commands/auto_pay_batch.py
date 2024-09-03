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
from notifications.views.core import (
    send_cobalt_email_with_template,
)
from payments.models import (
    OrgPaymentMethod,
)
from rbac.core import (
    rbac_get_group_by_name,
    rbac_get_users_in_group,
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

        rule = "members_edit"
        group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.{rule}")
        member_editors = rbac_get_users_in_group(group)

        email_body = render_to_string(
            "organisations/club_menu/members/auto_pay_club_email_content.html",
            {
                "club": club,
                "total_collected": total_collected,
                "paid_memberships": paid_memberships,
                "failed_memberships": failed_memberships,
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

        for user in member_editors:

            context["name"] = user.first_name

            send_cobalt_email_with_template(
                to_address=user.email,
                context=context,
            )

    def notify_member(self, club, membership):

        email_body = render_to_string(
            "organisations/club_menu/members/auto_pay_member_email_content.html",
            {
                "club": club,
                "membership": membership,
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
                        self.notify_member(club, membership)

                    else:
                        logger.warning(
                            f"Auto pay failed for {membership.user.system_number} '{message}'"
                        )
                        membership.message = message
                        failed_memberships.append(membership)

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
