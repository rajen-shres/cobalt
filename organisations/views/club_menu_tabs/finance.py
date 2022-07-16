from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from accounts.models import User
from cobalt.settings import GLOBAL_CURRENCY_SYMBOL, BRIDGE_CREDITS
from notifications.notifications_views.core import send_cobalt_email_to_system_number
from organisations.decorators import check_club_menu_access
from organisations.models import ClubLog, MemberMembershipType, Organisation
from organisations.views.club_menu import tab_finance_htmx
from payments.models import UserPendingPayment, OrganisationTransaction
from payments.payments_views.core import (
    update_account,
    update_organisation,
    org_balance,
)
from payments.payments_views.payments_api import payment_api_batch
from rbac.core import (
    rbac_get_users_with_role,
    rbac_user_has_role_exact,
    rbac_get_users_in_group_by_name,
)
from utils.utils import cobalt_paginator


@check_club_menu_access(check_payments=True)
def cancel_user_pending_debt_htmx(request, club):
    """Cancel a debt for a user"""

    user_pending_payment = get_object_or_404(
        UserPendingPayment, pk=request.POST.get("user_pending_payment_id")
    )
    if user_pending_payment.organisation != club:
        message = "This debt is not for this club"
    else:
        user_pending_payment.delete()
        message = "Pending payment deleted"

        ClubLog(
            organisation=club,
            actor=request.user,
            action=f"Cancelled debt for {user_pending_payment.system_number} for {GLOBAL_CURRENCY_SYMBOL}{user_pending_payment.amount:.2f}",
        ).save()

    return tab_finance_htmx(request, message=message)


@check_club_menu_access(check_payments=True)
def get_org_balance_htmx(request, club):
    """Show balance for this club"""

    last_tran = OrganisationTransaction.objects.filter(organisation=club).last()
    balance = last_tran.balance if last_tran else 0.0

    return HttpResponse(f"${balance:,.2f}")


@check_club_menu_access(check_payments=True)
def transactions_htmx(request, club):
    """handle the transaction listing part of the finance tab"""

    transactions = OrganisationTransaction.objects.filter(organisation=club).order_by(
        "-pk"
    )

    things = cobalt_paginator(request, transactions)

    hx_post = reverse("organisations:transactions_htmx")
    hx_target = "#id_finance_transactions"
    hx_vars = f"club_id: {club.id}"

    return render(
        request,
        "organisations/club_menu/finance/transactions_htmx.html",
        {
            "club": club,
            "things": things,
            "hx_post": hx_post,
            "hx_target": hx_target,
            "hx-vars": hx_vars,
        },
    )


@check_club_menu_access(check_payments=True)
def pay_member_htmx(request, club):
    """make a payment to a member"""

    if "save" not in request.POST:
        hx_post = reverse("organisations:pay_member_htmx")
        return render(
            request,
            "organisations/club_menu/finance/pay_member_htmx.html",
            {"club": club, "hx_post": hx_post},
        )

    member = get_object_or_404(User, pk=request.POST.get("member_id"))
    description = request.POST.get("description")
    amount = float(request.POST.get("amount"))

    if amount <= 0:
        return tab_finance_htmx(request, message="Amount was less than zero")

    if amount > org_balance(club):
        return tab_finance_htmx(
            request, message="Club has insufficient funds for this transfer"
        )

    # Pay user
    update_account(
        member=member,
        amount=amount,
        description=description,
        organisation=club,
        payment_type="Org Transfer",
    )

    # debit club
    update_organisation(
        organisation=club,
        amount=-amount,
        description=description,
        payment_type="Org Transfer",
        member=member,
    )

    # log it
    ClubLog(
        organisation=club,
        actor=request.user,
        action=f"Paid {GLOBAL_CURRENCY_SYMBOL}{amount:,.2f} to {member}",
    ).save()

    return tab_finance_htmx(
        request,
        message=f"Payment of {GLOBAL_CURRENCY_SYMBOL}{amount:,.2f} made to {member.full_name}",
    )


@check_club_menu_access(check_payments=True)
def charge_member_htmx(request, club):
    """make a charge to a member"""

    if "save" not in request.POST:
        hx_post = reverse("organisations:charge_member_htmx")
        return render(
            request,
            "organisations/club_menu/finance/charge_member_htmx.html",
            {"club": club, "hx_post": hx_post},
        )

    member = get_object_or_404(User, pk=request.POST.get("member_id"))
    description = request.POST.get("description")
    amount = float(request.POST.get("amount"))

    # Validate
    if amount <= 0:
        return tab_finance_htmx(request, message="Amount was less than zero")

    # Check membership
    if (
        not MemberMembershipType.objects.active()
        .filter(system_number=member.system_number)
        .exists()
    ):
        return tab_finance_htmx(
            request,
            message=f"{member} is not a member of the club. Cannot charge user.",
        )

    # Try to charge user
    if payment_api_batch(
        member=member,
        amount=amount,
        description=description,
        organisation=club,
        payment_type="Org Transfer",
    ):

        # log it
        ClubLog(
            organisation=club,
            actor=request.user,
            action=f"Charged {GLOBAL_CURRENCY_SYMBOL}{amount:,.2f} to {member}",
        ).save()

        # notify user
        msg = f"""{request.user} has charged {GLOBAL_CURRENCY_SYMBOL}{amount:,.2f} to your {BRIDGE_CREDITS}
        account for {description}.
            <br><br>If you have any queries please contact {club} in the first instance.
        """
        send_cobalt_email_to_system_number(
            system_number=member.system_number,
            subject=f"Charge from {club}",
            message=msg,
            club=club,
        )

        return tab_finance_htmx(
            request,
            message=f"Charge of {GLOBAL_CURRENCY_SYMBOL}{amount:,.2f} made to {member.full_name} via {BRIDGE_CREDITS}",
        )

    else:

        return tab_finance_htmx(
            request, message=f"Payment FAILED for {member.full_name}"
        )


@check_club_menu_access(check_payments=True)
def pay_org_htmx(request, club):
    """make a payment to another club"""

    if "save" not in request.POST:
        return render(
            request,
            "organisations/club_menu/finance/pay_org_htmx.html",
            {"club": club},
        )

    org = get_object_or_404(Organisation, pk=request.POST.get("org_id"))
    description = request.POST.get("description")
    amount = float(request.POST.get("amount"))

    # Validate
    if amount <= 0:
        return tab_finance_htmx(request, message="Amount was less than zero")

    if amount > org_balance(club):
        return tab_finance_htmx(
            request, message="Club has insufficient funds for this transfer"
        )

    # debit this club
    update_organisation(
        organisation=club,
        amount=-amount,
        description=description,
        payment_type="Org Transfer",
        other_organisation=org,
    )

    # credit other club
    update_organisation(
        organisation=org,
        amount=amount,
        description=description,
        payment_type="Org Transfer",
        other_organisation=club,
    )

    # log it
    ClubLog(
        organisation=club,
        actor=request.user,
        action=f"Transferred {GLOBAL_CURRENCY_SYMBOL}{amount:,.2f} to {org}",
    ).save()

    # notify payments users at other club, not general admins though
    # There is no really clean way to do this. We use the rbac tree to find either the basic group (basic RBAC) or
    # the payments_edit group (advanced RBAC).

    # try basic
    other_club_admins = rbac_get_users_in_group_by_name(
        f"{club.rbac_name_qualifier}.basic"
    )

    if not other_club_admins:
        # try advanced
        other_club_admins = rbac_get_users_in_group_by_name(
            f"{club.rbac_name_qualifier}payments_edit"
        )

    for other_club_admin in other_club_admins:

        print(other_club_admin)

        msg = f"""{request.user} from {club} has paid {GLOBAL_CURRENCY_SYMBOL}{amount:,.2f} into the {BRIDGE_CREDITS}
        account for {org}. The description was: {description}.
            <br><br>If you have any queries please contact {club} in the first instance.
        """
        send_cobalt_email_to_system_number(
            system_number=other_club_admin.system_number,
            subject=f"Transfer from {club}",
            message=msg,
            club=club,
        )

    return tab_finance_htmx(
        request,
        message=f"Transfer of {GLOBAL_CURRENCY_SYMBOL}{amount:,.2f} made to {org} via {BRIDGE_CREDITS}",
    )
