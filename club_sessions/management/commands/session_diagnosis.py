"""
A tool to provide information about a session's entries and payments to help
diagnose issues
"""

import sys
from datetime import timedelta

from django.core.management.base import BaseCommand

from club_sessions.models import Session, SessionEntry, SessionMiscPayment
from accounts.models import User, UnregisteredUser
from organisations.models import Organisation
from payments.models import OrgPaymentMethod, MemberTransaction


class Command(BaseCommand):
    help = "Diagnistic information about a sessions entries and payments"

    def add_arguments(self, parser):
        parser.add_argument("session_id", nargs=1, type=int, help="Session id")

    def handle(self, *args, **options):

        session = Session.objects.get(pk=options["session_id"][0])

        club = session.session_type.organisation

        suspect_members = []

        self.stdout.write("Session Diagnostics\n")
        self.stdout.write("===================\n\n")

        self.stdout.write(f"Session  : {session}   [id={session.id}]\n")
        self.stdout.write(f"Club     : {club}   [id={club.id}]\n")
        self.stdout.write(f"Director : {session.director.full_name}\n")
        self.stdout.write(f"   Email : {session.director.email}\n\n")

        bc_payment_method = OrgPaymentMethod.objects.filter(
            active=True, organisation=club, payment_method="Bridge Credits"
        ).first()

        if not bc_payment_method:
            self.stdout.write("Club is not configured for Bridge Credits\n")
            sys.exit()

        bc_session_enties = SessionEntry.objects.filter(
            session=session,
            payment_method=bc_payment_method,
        ).order_by("system_number")

        bc_session_enties_nos = bc_session_enties.values_list(
            "system_number", flat=True
        )

        member_txns = MemberTransaction.objects.filter(
            club_session_id=session.id,
        ).order_by("member__system_number")

        member_txns_nos = member_txns.values_list("member__system_number", flat=True)

        self.stdout.write("Paying by Bridge Credits:\n".upper())
        header = f"{'System no':12}  {'Id':6}  {'Name':20}  {'Fee':8}  Paid   Txn?"
        self.stdout.write(f"{header}\n")
        self.stdout.write(f"{'-' * len(header)}\n")

        bc_table_money_payments = 0
        bc_table_money = 0
        for se in bc_session_enties:
            user = User.objects.get(system_number=se.system_number)
            self.stdout.write(
                f"{se.system_number:<12}  {user.id:<6}  {user.full_name:20}  {se.fee:>8.2f}  {'Yes ' if se.is_paid else 'No  '}   {'Yes' if se.system_number in member_txns_nos else 'No  '}\n"
            )
            if se.is_paid:
                bc_table_money_payments += 1
                bc_table_money += se.fee
                if se.system_number not in member_txns_nos:
                    if user not in suspect_members:
                        suspect_members.append(user)

        self.stdout.write(f"{'-' * len(header)}\n")
        self.stdout.write(
            f"{bc_table_money_payments:6} Bridge Credits payments made, total: {bc_table_money:>8.2f}\n\n"
        )

        nonbc_session_entries = (
            SessionEntry.objects.select_related("payment_method")
            .filter(
                session=session,
            )
            .exclude(
                payment_method=bc_payment_method,
            )
            .order_by("system_number")
        )

        self.stdout.write("Other Payment Methods:\n".upper())
        header = f"{'System no':12}  Type   {'Id':6}  {'Name':20}  {'Fee':8}  {'Method':15}  Paid"
        self.stdout.write(f"{header}\n")
        self.stdout.write(f"{'-' * len(header)}\n")

        nonbc_table_money_payments = 0
        nonbc_table_money = 0
        for se in nonbc_session_entries:
            player_type = "*UNK*"
            player_name = se.player_name_from_file
            player_id = 0
            player = User.objects.filter(system_number=se.system_number).first()
            if player:
                player_type = "User "
                player_name = player.full_name
                player_id = player.id
            else:
                player = UnregisteredUser.objects.filter(
                    system_number=se.system_number
                ).first()
                if player:
                    player_type = "Unreg"
                    player_name = player.full_name
                    player_id = player.id

            self.stdout.write(
                f"{se.system_number:<12}  {player_type}  {player_id:<6}  {player_name:20}  {se.fee:>8.2f}  {se.payment_method.payment_method:15}  {'Yes' if se.is_paid else 'No'}\n"
            )
            if se.is_paid:
                nonbc_table_money_payments += 1
                nonbc_table_money += se.fee

        self.stdout.write(f"{'-' * len(header)}\n")
        self.stdout.write(
            f"{nonbc_table_money_payments:22} other payments made, total: {nonbc_table_money:>8.2f}\n\n"
        )

        # misc items

        bc_misc_items = (
            SessionMiscPayment.objects.filter(
                session_entry__session=session,
                payment_made=True,
                payment_method=bc_payment_method,
            )
            .select_related("session_entry")
            .order_by("session_entry__system_number")
        )

        if bc_misc_items.count():

            self.stdout.write("Misc Items by Bridge Credits:\n".upper())
            header = f"{'System no':12}  {'Id':6}  {'Name':20}  {'Amount':8}  {'Description':20}  Paid"
            self.stdout.write(f"{header}\n")
            self.stdout.write(f"{'-' * len(header)}\n")

            total_misc_bc = 0
            for mi in bc_misc_items:
                user = User.objects.get(system_number=mi.session_entry.system_number)
                self.stdout.write(
                    f"{user.system_number:<12}  {user.id:<6}  {user.full_name:20}  {mi.amount:>8.2f}  {mi.description:20}  {'Yes ' if mi.is_paid else 'No  '}\n"
                )
                if mi.is_paid:
                    total_misc_bc += mi.amount

            self.stdout.write(f"{'-' * len(header)}\n")
            self.stdout.write(
                f"{bc_table_money_payments:6} Bridge Credits payments made, total: {bc_table_money:>8.2f}\n\n"
            )

        else:

            total_misc_bc = 0
            self.stdout.write("No Misc Items by Bridge Credits found\n\n".upper())

        # member transactions (ie actual payments)

        self.stdout.write("Member Transactions:\n".upper())
        header = f"{'System no':12}  {'Id':6}  {'Name':20}  {'Amount':8}  {'Description':20}  Entry?   Dup?"
        self.stdout.write(f"{header}\n")
        self.stdout.write(f"{'-' * len(header)}\n")

        mt_payments = 0
        mt_count_by_sysno = {}
        for mt in member_txns:
            mt_payments += mt.amount
            if mt.member.system_number in mt_count_by_sysno:
                mt_count_by_sysno[mt.member.system_number] += 1
                is_dup = True
                if mt.member not in suspect_members:
                    suspect_members.append(mt.member)
            else:
                mt_count_by_sysno[mt.member.system_number] = 1
                is_dup = False

            self.stdout.write(
                f"{mt.member.system_number:12}  {mt.member.id:6}  {mt.member.full_name:20}  {mt.amount:8.2f}  {mt.description[:15]:20}  {'Yes ' if mt.member.system_number in bc_session_enties_nos else 'No  '}   {'Yes' if is_dup else ''}\n"
            )

            if mt.member.system_number not in bc_session_enties_nos:
                if mt.member not in suspect_members:
                    suspect_members.append(mt.member)

        self.stdout.write(f"{'-' * len(header)}\n")
        self.stdout.write(
            f"{len(suspect_members):10} duplicate found, Total payments: {mt_payments:>8.2f}\n\n"
        )

        # show recent transactions for the members with duplicates

        if len(suspect_members) > 0:

            self.stdout.write(
                "Recent Transactions for members with duplicates or missing transactions:\n\n".upper()
            )

            for user in suspect_members:

                recent_txns = MemberTransaction.objects.filter(
                    member=user,
                    created_date__date__gte=session.session_date,
                    created_date__date__lte=session.session_date + timedelta(days=5),
                    organisation=club,
                )

                self.stdout.write(f"{user.system_number} {user.full_name}\n")
                header = f"{'Date':12}  {'Amount':8}  {'Balance':8}  {'Description':20}  {'Type':20}"
                self.stdout.write(f"{header}\n")
                self.stdout.write(f"{'-' * len(header)}\n")

                for rt in recent_txns:
                    self.stdout.write(
                        f"{rt.created_date.strftime('%d-%m-%Y'):12}  {rt.amount:8.2f}  {rt.balance:8.2f}  {rt.description:20}  {rt.type:20}"
                    )

                self.stdout.write(f"{'-' * len(header)}\n\n")

        # refunds

        refunds = MemberTransaction.objects.filter(
            description__startswith=f"Bridge Credits returned for {session.description}",
            created_date__date__gte=session.session_date,
            created_date__date__lte=session.session_date + timedelta(days=5),
            organisation=club,
        )

        if refunds.count():

            self.stdout.write("Refunds:\n".upper())

            header = f"{'Date':12}  {'Amount':8}  {'Balance':8}  {'Description':20}  {'Type':20}"
            self.stdout.write(f"{header}\n")
            self.stdout.write(f"{'-' * len(header)}\n")

            total_refunds = 0
            for refund in refunds:
                self.stdout.write(
                    f"{refund.created_date:12}  {refund.amount:8.2f}  {refund.balance:8.2f}  {refund.description:20}  {refund.type:20}"
                )
                total_refunds += refund.amount

            self.stdout.write(f"{'-' * len(header)}\n\n")

        else:

            total_refunds = 0
            self.stdout.write("No Refunds found\n\n".upper())

        self.stdout.write("Summary:\n\n".upper())

        self.stdout.write(
            f"{'Total table money - paid by bridge credits':60} : {bc_table_money:8.2f}\n"
        )
        self.stdout.write(
            f"{'Total misc items - paid by bridge credits':60} : {total_misc_bc:8.2f}\n"
        )
        self.stdout.write(
            f"{'Expected net Bridge Credit payments ':60} : {bc_table_money + total_misc_bc :8.2f}\n\n"
        )
        self.stdout.write(f"{'Bridge Credit payments':60} : {mt_payments:8.2f}\n")
        self.stdout.write(f"{'Bridge Credit refunds':60} : {total_refunds:8.2f}\n")
        self.stdout.write(
            f"{'Net Bridge Credits received':60} : {mt_payments + total_refunds:8.2f}\n\n"
        )

        discrepancy = bc_table_money + total_misc_bc + mt_payments + total_refunds

        if discrepancy > 0:
            self.stdout.write(f"{'UNDER-PAYMENT DETECTED':60} : {discrepancy:8.2f}\n")
        elif discrepancy < 0:
            self.stdout.write(f"{'OVER-PAYMENT DETECTED':60} : {-discrepancy:8.2f}\n")
        else:
            self.stdout.write("Bridge credits balanced\n")

        self.stdout.write(
            f"\n{'Total table money - paid by other methods':60} : {nonbc_table_money:8.2f}\n"
        )
