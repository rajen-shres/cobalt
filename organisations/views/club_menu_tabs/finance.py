from itertools import chain

from django.db.models import Sum, Min
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from accounts.models import User
from club_sessions.models import Session
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


@check_club_menu_access(check_payments_view=True)
def transactions_htmx(request, club):
    """handle the transaction listing part of the finance tab"""

    summarise = request.POST.get("summarise")
    if not summarise:
        summarise = request.GET.get("summarise")

    # Set htmx paginate value too
    searchparams = f"summarise={summarise}&"

    # We want to summarise sessions if requested
    if not summarise:
        transactions = OrganisationTransaction.objects.filter(
            organisation=club
        ).order_by("-pk")
        things = cobalt_paginator(request, transactions)

    else:
        things = _transactions_with_sessions(request, club)

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
            "hx_vars": hx_vars,
            "searchparams": searchparams,
            "summarise": summarise,
        },
    )


def _transactions_with_sessions(request, club):
    """handle mixing summary lines for sessions with general transactions. Instead of a line for each user, we want
    to have a summary of the session
    """

    # First get transactions without sessions and create this page
    no_session_transactions = OrganisationTransaction.objects.filter(
        organisation=club, club_session_id=None
    ).order_by("-pk")
    no_session_things = cobalt_paginator(request, no_session_transactions)

    # Now get the session transactions on their own and paginate
    session_transactions = (
        OrganisationTransaction.objects.filter(organisation=club)
        .exclude(club_session_id=None)
        .order_by("-club_session_id")
        .values("description", "club_session_id")
        .annotate(amount=Sum("amount"))
        .annotate(created_date=Min("created_date"))
    )
    session_things = cobalt_paginator(request, session_transactions)

    # Now we need to combine two quite different things with common fields

    # start with no_session_things
    things = [
        {
            "pk": no_session_thing.pk,
            "id": no_session_thing.pk,
            "created_date": no_session_thing.created_date,
            "description": no_session_thing.description,
            "member": no_session_thing.member,
            "other_organisation": no_session_thing.other_organisation,
            "amount": no_session_thing.amount,
            "balance": no_session_thing.balance,
        }
        for no_session_thing in no_session_things
    ]

    # add in session details
    for session_thing in session_things:
        thing = {
            "description": session_thing["description"],
            "amount": session_thing["amount"],
            "created_date": session_thing["created_date"],
            "member": "--Session--",
            "club_session_id": session_thing["club_session_id"],
        }
        things.append(thing)

    # Sort by date
    things.sort(key=lambda x: x["created_date"], reverse=True)

    # Now we want to change it to a paginating object again
    page_things = cobalt_paginator(request, things)

    # TODO: Check if this actually works
    page_things.has_previous = (
        no_session_things.has_previous or session_things.has_previous
    )
    page_things.has_next = no_session_things.has_next or session_things.has_next

    return page_things


def pay_member_from_organisation(request, club, amount, description, member):
    """Pay a member from an organisation's account. Calling module is responsible for security.

    This works off the request object.

    Request should have member_id, description and amount. Although description can be overridden as a parameter

    Return: status, message

    Status is True/False for success
    Message contains tet narrative

    """

    if amount <= 0:
        return False, "Amount was less than zero"

    if amount > org_balance(club):
        return False, "Club has insufficient funds for this transfer"

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

    return (
        True,
        f"Payment of {GLOBAL_CURRENCY_SYMBOL}{amount:,.2f} made to {member.full_name}",
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
    amount = float(request.POST.get("amount"))
    description = request.POST.get("description")

    _, message = pay_member_from_organisation(
        request, club, amount, description, member
    )

    return tab_finance_htmx(request, message=message)


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
    if not MemberMembershipType.objects.filter(
        system_number=member.system_number
    ).exists():
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
            request,
            message=f"Payment FAILED for {member.full_name}. Insufficient funds.",
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

    if org == club:
        return tab_finance_htmx(
            request, message="Ignoring attempt to transfer to yourself"
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
            f"{club.rbac_name_qualifier}.payments_edit"
        )

    for other_club_admin in other_club_admins:

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


@check_club_menu_access(check_payments=True)
def transaction_details_htmx(request, club):
    """return details of a transaction"""

    trans = get_object_or_404(OrganisationTransaction, pk=request.POST.get("trans_id"))
    if trans.organisation != club:
        return HttpResponse("Transaction does not belong to this club")

    return render(
        request,
        "organisations/club_menu/finance/transaction_detail_htmx.html",
        {"club": club, "trans": trans},
    )


@check_club_menu_access(check_payments=True)
def transaction_session_details_htmx(request, club):
    """return details of a session"""

    club_session = get_object_or_404(Session, pk=request.POST.get("club_session_id"))
    session_transactions = OrganisationTransaction.objects.filter(
        organisation=club, club_session_id=club_session.id
    )
    # trans = get_object_or_404(OrganisationTransaction, pk=request.POST.get("trans_id"))
    # if trans.organisation != club:
    #     return HttpResponse("Transaction does not belong to this club")

    return render(
        request,
        "organisations/club_menu/finance/transaction_session_detail_htmx.html",
        {
            "club": club,
            "club_session": club_session,
            "session_transactions": session_transactions,
        },
    )
