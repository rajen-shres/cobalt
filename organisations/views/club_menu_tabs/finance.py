from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db.models import Sum, Min
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from accounts.models import User
from club_sessions.models import Session
from cobalt.settings import GLOBAL_CURRENCY_SYMBOL, BRIDGE_CREDITS
from events.models import Event
from notifications.views.core import send_cobalt_email_to_system_number
from organisations.decorators import check_club_menu_access
from organisations.models import ClubLog, MemberMembershipType, Organisation
from organisations.views.club_menu import tab_finance_htmx
from organisations.views.club_menu_tabs.members import edit_member_htmx
from payments.models import UserPendingPayment, OrganisationTransaction
from payments.views.core import (
    update_account,
    update_organisation,
    org_balance,
)
from payments.views.org_report.csv import organisation_transactions_csv_download
from payments.views.org_report.data import (
    organisation_transactions_by_date_range,
    sessions_and_payments_by_date_range,
    event_payments_summary_by_date_range,
    combined_view_events_sessions_other,
)
from payments.views.org_report.xls import organisation_transactions_xls_download
from payments.views.payments_api import payment_api_batch
from rbac.core import (
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

    # We get called from the member page too, check if we should return the member view or default ot finance
    if request.POST.get("return_member_tab"):
        return edit_member_htmx(request, message=message)

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

    # Get view type - default to all
    view_type = request.POST.get("view_type", "all")

    if view_type == "session":
        things = _summary_by_sessions(request, club)

    elif view_type == "event":
        things = _summary_by_events(request, club)

    elif view_type == "other":
        transactions = (
            OrganisationTransaction.objects.filter(organisation=club)
            .filter(event_id__isnull=True)
            .filter(club_session_id__isnull=True)
            .order_by("-pk")
        )
        things = cobalt_paginator(request, transactions)

    else:  # all
        transactions = OrganisationTransaction.objects.filter(
            organisation=club
        ).order_by("-pk")
        things = cobalt_paginator(request, transactions)

    hx_post = reverse("organisations:transactions_htmx")
    hx_target = "#id_finance_transactions"
    hx_vars = f"club_id: {club.id}, view_type: '{view_type}'"

    return render(
        request,
        "organisations/club_menu/finance/transactions_htmx.html",
        {
            "club": club,
            "things": things,
            "hx_post": hx_post,
            "hx_target": hx_target,
            "hx_vars": hx_vars,
            "view_type": view_type,
        },
    )


def _summary_by_sessions(request, club):
    """Summarise by session only"""

    # Get the session transactions on their own and paginate
    session_transactions = (
        OrganisationTransaction.objects.filter(organisation=club)
        .exclude(club_session_id=None)
        .order_by("-club_session_id")
        .values("description", "club_session_id")
        .annotate(amount=Sum("amount"))
        .annotate(created_date=Min("created_date"))
    )

    return cobalt_paginator(request, session_transactions)


def _summary_by_events(request, club):
    """Summarise by event only"""

    # TODO: This loads all events for an organisation since the start of time. Probably okay for many years, but
    # may need fixed later.

    # Get the event transactions on their own and paginate
    event_transactions = (
        OrganisationTransaction.objects.filter(organisation=club)
        .exclude(event_id=None)
        .order_by("-event_id")
        .values("event_id")
        .annotate(amount=Sum("amount"))
        .annotate(created_date=Min("created_date"))
    )

    # Get event names
    event_ids = event_transactions.values_list("event_id")
    event_names = Event.objects.filter(id__in=event_ids).values(
        "id", "congress__name", "event_name"
    )

    event_names_dict = {}
    for event_name in event_names:
        event_names_dict[
            event_name["id"]
        ] = f"{event_name['congress__name']} - {event_name['event_name']}"

    # Augment data
    for event_transaction in event_transactions:
        event_transaction["description"] = event_names_dict[
            event_transaction["event_id"]
        ]

    return cobalt_paginator(request, event_transactions)


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

    # notify user
    msg = f"""{request.user} has paid {GLOBAL_CURRENCY_SYMBOL}{amount:,.2f} to your {BRIDGE_CREDITS}
    account for {description}.
        <br><br>If you have any queries please contact {club} in the first instance.
    """
    send_cobalt_email_to_system_number(
        system_number=member.system_number,
        subject=f"Charge from {club}",
        message=msg,
        club=club,
    )

    return (
        True,
        f"Payment of {GLOBAL_CURRENCY_SYMBOL}{amount:,.2f} made to {member.full_name}",
    )


def top_up_member_from_organisation(request, club, amount, description, member):
    """Pay a member from an organisation's account when a top up is made. Calling module is responsible for security.

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
        payment_type="Club Top Up",
    )

    # debit club
    update_organisation(
        organisation=club,
        amount=-amount,
        description=description,
        payment_type="Club Top Up",
        member=member,
    )

    # log it
    ClubLog(
        organisation=club,
        actor=request.user,
        action=f"Made top up payment of {GLOBAL_CURRENCY_SYMBOL}{amount:,.2f} to {member}",
    ).save()

    return (
        True,
        f"Top Up of {GLOBAL_CURRENCY_SYMBOL}{amount:,.2f} made to {member.full_name}",
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


def _download_xls(request, club, start_date, end_date):
    """download statement data in XLS format"""

    return HttpResponse("XLS download")


@check_club_menu_access(check_payments=True)
def transaction_filter_htmx(request, club):
    """tab for CSV downloads and filtered view"""

    start_date = request.POST.get("start_date")
    end_date = request.POST.get("end_date")
    description_search = request.POST.get("description_search")
    view_type_selector = request.POST.get("view_type_selector")

    if not view_type_selector:
        # first call - show blank form
        return render(
            request,
            "organisations/club_menu/finance/transaction_filter_htmx.html",
            {"club": club},
        )

    if not start_date or not end_date:
        return HttpResponse("Enter dates to perform search")

    if "download-csv" in request.POST:
        return organisation_transactions_csv_download(
            request, club, start_date, end_date, description_search
        )

    if "download-xls" in request.POST:
        return organisation_transactions_xls_download(
            request, club, start_date, end_date, description_search
        )

    if "show_filtered_data" in request.POST:
        return organisation_transactions_filtered_data(
            request, club, start_date, end_date, description_search, view_type_selector
        )

    return HttpResponse("an error occurred")


def organisation_transactions_filtered_data(
    request, club, start_date, end_date, description_search, view_type_selector
):
    """show filtered data (date and search) on screen, not as CSV/XLS download"""

    # set up data for pagination footer
    hx_post = reverse("organisations:transaction_filter_htmx")
    hx_target = "#id_filtered_transactions"
    hx_vars = f"club_id: {club.id}, show_filtered_data: 1, start_date: '{start_date}', end_date: '{end_date}', view_type_selector: '{view_type_selector}'"
    if description_search:
        hx_vars = f"{hx_vars}, description_search: '{description_search}'"

    if view_type_selector == "all":

        organisation_transactions = organisation_transactions_by_date_range(
            club, start_date, end_date, description_search, augment_data=False
        )

        things = cobalt_paginator(request, organisation_transactions, 50)

        return render(
            request,
            "organisations/club_menu/finance/organisation_transactions_filtered_data_all_htmx.html",
            {
                "club": club,
                "things": things,
                "organisation_transactions": organisation_transactions,
                "hx_target": hx_target,
                "hx_post": hx_post,
                "hx_vars": hx_vars,
            },
        )

    elif view_type_selector == "session":

        # Get data
        sessions_in_range, payments_dict = sessions_and_payments_by_date_range(
            club, start_date, end_date
        )

        # Add session total amount to data
        for session_in_range_id in sessions_in_range:
            sessions_in_range[session_in_range_id].amount = payments_dict.get(
                session_in_range_id, "No Payments"
            )

        # Paginate
        list_of_sessions = list(sessions_in_range.values())
        list_of_sessions.reverse()
        things = cobalt_paginator(request, list_of_sessions)

        return render(
            request,
            "organisations/club_menu/finance/organisation_transactions_filtered_data_sessions_htmx.html",
            {
                "club": club,
                "things": things,
                "hx_target": hx_target,
                "hx_post": hx_post,
                "hx_vars": hx_vars,
            },
        )

    elif view_type_selector == "event":

        event_data = event_payments_summary_by_date_range(club, start_date, end_date)

        list_of_events = list(event_data.values())
        list_of_events.reverse()
        things = cobalt_paginator(request, list_of_events)

        return render(
            request,
            "organisations/club_menu/finance/organisation_transactions_filtered_data_events_htmx.html",
            {
                "club": club,
                "things": things,
                "hx_target": hx_target,
                "hx_post": hx_post,
                "hx_vars": hx_vars,
            },
        )

    elif view_type_selector == "combined":

        organisation_transactions = combined_view_events_sessions_other(
            club, start_date, end_date
        )

        # this is a tuple, convert to a list
        data = [
            organisation_transaction[1]
            for organisation_transaction in organisation_transactions
        ]
        data.reverse()
        things = cobalt_paginator(request, data)

        return render(
            request,
            "organisations/club_menu/finance/organisation_transactions_filtered_data_combined_htmx.html",
            {
                "club": club,
                "things": things,
                "hx_target": hx_target,
                "hx_post": hx_post,
                "hx_vars": hx_vars,
            },
        )

    else:
        return HttpResponse("No view provided")
