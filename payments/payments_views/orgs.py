import csv
import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.template.loader import render_to_string
from django.utils import timezone, dateformat

from cobalt.settings import GLOBAL_CURRENCY_SYMBOL, BRIDGE_CREDITS, COBALT_HOSTNAME
from notifications.notifications_views.core import contact_member

from organisations.models import Organisation
from organisations.views.general import org_balance
from payments.forms import MemberTransferOrg
from payments.models import OrganisationTransaction
from payments.payments_views.core import update_organisation, update_account, TZ
from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden
from utils.utils import cobalt_paginator


@login_required()
def statement_org(request, org_id):
    """Organisation statement view.

    Basic view of statement showing transactions in a web page.

    Args:
        request: standard request object
        org_id: organisation to view

    Returns:
        HTTPResponse

    """

    organisation = get_object_or_404(Organisation, pk=org_id)

    admin_view = rbac_user_has_role(request.user, "payments.global.view")

    if (
        not rbac_user_has_role(request.user, "payments.manage.%s.view" % org_id)
        and not rbac_user_has_role(request.user, "payments.manage.%s.edit" % org_id)
        and not admin_view
    ):
        return rbac_forbidden(request, "payments.manage.%s.view" % org_id)

    # get balance
    balance = org_balance(organisation, True)

    # get summary
    today = timezone.now()
    ref_date = today - datetime.timedelta(days=30)
    summary = (
        OrganisationTransaction.objects.filter(
            organisation=organisation, created_date__gte=ref_date
        )
        .values("type")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )

    total = 0.0
    for item in summary:
        total += float(item["total"])

    # get details
    events_list = OrganisationTransaction.objects.filter(
        organisation=organisation
    ).order_by("-created_date")

    things = cobalt_paginator(request, events_list)

    page_balance = {}

    if things:
        page_balance["closing_balance"] = things[0].balance
        page_balance["closing_date"] = things[0].created_date
        earliest = things[len(things) - 1]
        page_balance["opening_balance"] = earliest.balance - earliest.amount
        page_balance["opening_date"] = earliest.created_date

    return render(
        request,
        "payments/orgs/statement_org.html",
        {
            "things": things,
            "balance": balance,
            "org": organisation,
            "summary": summary,
            "total": total,
            "page_balance": page_balance,
            "admin_view": admin_view,
        },
    )


@login_required()
def statement_csv_org(request, org_id):
    """Organisation statement CSV.

    Args:
        request: standard request object
        org_id: organisation to view

    Returns:
        HTTPResponse: CSV

    """

    organisation = get_object_or_404(Organisation, pk=org_id)

    if not rbac_user_has_role(request.user, "payments.manage.%s.view" % org_id):
        if not rbac_user_has_role(request.user, "payments.global.view"):
            return rbac_forbidden(request, "payments.manage.%s.view" % org_id)

    # get details
    events_list = OrganisationTransaction.objects.filter(
        organisation=organisation
    ).order_by("-created_date")

    local_dt = timezone.localtime(timezone.now(), TZ)
    today = dateformat.format(local_dt, "Y-m-d H:i:s")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="statement.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [organisation.name, "Downloaded by %s" % request.user.full_name, today]
    )
    writer.writerow(
        [
            "Date",
            "Counterparty",
            "Reference",
            "Type",
            "Description",
            "Amount",
            "Balance",
        ]
    )

    for row in events_list:
        counterparty = ""
        if row.member:
            counterparty = row.member
        if row.other_organisation:
            counterparty = row.other_organisation

        local_dt = timezone.localtime(row.created_date, TZ)
        writer.writerow(
            [
                dateformat.format(local_dt, "Y-m-d H:i:s"),
                counterparty,
                row.reference_no,
                row.type,
                row.description,
                row.amount,
                row.balance,
            ]
        )

    return response


def statement_org_summary_ajax(request, org_id, range):
    """Called by the org statement when the summary date range changes

    Args:
        request (HTTPRequest): standard request object
        org_id(int): pk of the org to query
        range(str): range to include in summary

    Returns:
        HTTPResponse: data for table

    """
    if request.method == "GET":

        organisation = get_object_or_404(Organisation, pk=org_id)

        if (
            not rbac_user_has_role(request.user, "payments.manage.%s.view" % org_id)
            and not rbac_user_has_role(request.user, "payments.manage.%s.edit" % org_id)
            and not rbac_user_has_role(request.user, "payments.global.view")
        ):
            return rbac_forbidden(request, "payments.manage.%s.view" % org_id)

        if range == "All":
            summary = (
                OrganisationTransaction.objects.filter(organisation=organisation)
                .values("type")
                .annotate(total=Sum("amount"))
                .order_by("-total")
            )
        else:
            days = int(range)
            today = timezone.now()
            ref_date = today - datetime.timedelta(days=days)
            summary = (
                OrganisationTransaction.objects.filter(
                    organisation=organisation, created_date__gte=ref_date
                )
                .values("type")
                .annotate(total=Sum("amount"))
                .order_by("-total")
            )

    total = 0.0
    for item in summary:
        total += float(item["total"])

    return render(
        request,
        "payments/orgs/statement_org_summary_ajax.html",
        {"summary": summary, "total": total},
    )


@login_required()
def member_transfer_org(request, org_id):
    """Allows an organisation to transfer money to a member

    Args:
        request (HTTPRequest): standard request object
        org_id (int): organisation doing the transfer

    Returns:
        HTTPResponse
    """

    organisation = get_object_or_404(Organisation, pk=org_id)

    if not rbac_user_has_role(
        request.user, "payments.manage.%s.edit" % org_id
    ) and not rbac_user_has_role(request.user, "payments.global.edit"):
        return rbac_forbidden(request, "payments.manage.%s.edit" % org_id)

    balance = org_balance(organisation)

    if request.method == "POST":
        form = MemberTransferOrg(request.POST, balance=balance)
        if form.is_valid():
            member = form.cleaned_data["transfer_to"]
            amount = form.cleaned_data["amount"]
            description = form.cleaned_data["description"]

            # Org transaction
            update_organisation(
                organisation=organisation,
                description=description,
                amount=-amount,
                payment_type="Member Transfer",
                member=member,
            )

            update_account(
                member=member,
                amount=amount,
                description=description,
                payment_type="Org Transfer",
                organisation=organisation,
            )

            # Notify member
            email_body = f"""<b>{organisation}</b> has transferred {GLOBAL_CURRENCY_SYMBOL}{amount:.2f}
                            into your {BRIDGE_CREDITS} account.
                            <br><br>
                            The description was: {description}.
                            <br><br>
                            Please contact {organisation} directly if you have any queries.
                            This transfer was made by {request.user}.
                            <br><br>"""

            # send
            contact_member(
                member=member,
                msg="Transfer from %s - %s%s"
                % (organisation, GLOBAL_CURRENCY_SYMBOL, amount),
                contact_type="Email",
                html_msg=email_body,
                link="/payments",
                subject="Transfer from %s" % organisation,
            )

            msg = "Transferred %s%s to %s" % (
                GLOBAL_CURRENCY_SYMBOL,
                amount,
                member,
            )
            messages.success(request, msg, extra_tags="cobalt-message-success")
            return redirect("payments:statement_org", org_id=organisation.id)
        else:
            print(form.errors)
    else:
        form = MemberTransferOrg(balance=balance)

    return render(
        request,
        "payments/orgs/member_transfer_org.html",
        {"form": form, "balance": balance, "org": organisation},
    )


@login_required()
def get_org_fees(request, org_id):
    """Get the ABF fees associated with this organisation"""

    org = get_object_or_404(Organisation, pk=org_id)
    return HttpResponse(org.settlement_fee_percent)
