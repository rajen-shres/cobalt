import csv
import datetime

import stripe
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.db.transaction import atomic
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.template.loader import render_to_string
from django.utils import timezone, dateformat
from django.utils.timezone import make_aware

from accounts.models import User
from cobalt.settings import (
    STRIPE_SECRET_KEY,
    GLOBAL_CURRENCY_SYMBOL,
    BRIDGE_CREDITS,
    COBALT_HOSTNAME,
    GLOBAL_ORG_ID,
    GLOBAL_ORG,
)
from logs.views import log_event
from masterpoints.views import user_summary
from notifications.views import contact_member
from organisations.models import Organisation
from payments.forms import (
    DateForm,
    StripeRefund,
    PaymentStaticForm,
    OrgStaticOverrideForm,
    SettlementForm,
    AdjustMemberForm,
    AdjustOrgForm,
)
from payments.models import (
    MemberTransaction,
    OrganisationTransaction,
    StripeTransaction,
    PaymentStatic,
    OrganisationSettlementFees,
)
from payments.payments_views.core import (
    stripe_current_balance,
    get_balance,
    update_organisation,
    update_account,
    TZ,
    statement_common,
)
from rbac.core import rbac_user_has_role
from rbac.decorators import rbac_check_role
from rbac.views import rbac_forbidden
from utils.utils import cobalt_paginator


@rbac_check_role("payments.global.view")
def statement_admin_view(request, member_id):
    """Member statement view for administrators.

    Basic view of statement showing transactions in a web page. Used by an
    administrator to view a members statement

    Args:
        request - standard request object

    Returns:
        HTTPResponse

    """

    user = get_object_or_404(User, pk=member_id)
    (summary, club, balance, auto_button, events_list) = statement_common(user)

    things = cobalt_paginator(request, events_list)

    # See if this admin can process refunds
    refund_administrator = rbac_user_has_role(request.user, "payments.global.edit")

    return render(
        request,
        "payments/players/statement.html",
        {
            "things": things,
            "user": user,
            "summary": summary,
            "club": club,
            "balance": balance,
            "auto_button": auto_button,
            "auto_amount": user.auto_amount,
            "refund_administrator": refund_administrator,
            "admin_view": True,
        },
    )


@rbac_check_role("payments.global.view")
def statement_admin_summary(request):
    """Main statement page for system administrators

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    # Member summary
    total_members = User.objects.count()
    auto_top_up = User.objects.filter(stripe_auto_confirmed="On").count()

    members_list = MemberTransaction.objects.order_by(
        "member", "-created_date"
    ).distinct("member")

    # exclude zeros
    total_balance_members_list = []
    for member in members_list:
        if member.balance != 0:
            total_balance_members_list.append(member)

    total_balance_members = 0
    members_with_balances = 0
    for item in total_balance_members_list:
        total_balance_members += item.balance
        members_with_balances += 1

    # Organisation summary
    total_orgs = Organisation.objects.count()

    orgs_list = OrganisationTransaction.objects.order_by(
        "organisation", "-created_date"
    ).distinct("organisation")

    # exclude zeros
    total_balance_orgs_list = []
    for org in orgs_list:
        if org.balance != 0:
            total_balance_orgs_list.append(org)

    orgs_with_balances = 0
    total_balance_orgs = 0
    for item in total_balance_orgs_list:
        total_balance_orgs += item.balance
        orgs_with_balances += 1

    # Stripe Summary
    today = timezone.now()
    ref_date = today - datetime.timedelta(days=30)
    stripe = (
        StripeTransaction.objects.filter(created_date__gte=ref_date)
        .exclude(stripe_method=None)
        .aggregate(Sum("amount"))
    )

    stripe_balance = stripe_current_balance()

    return render(
        request,
        "payments/admin/statement_admin_summary.html",
        {
            "total_members": total_members,
            "auto_top_up": auto_top_up,
            "total_balance_members": total_balance_members,
            "total_orgs": total_orgs,
            "total_balance_orgs": total_balance_orgs,
            "members_with_balances": members_with_balances,
            "orgs_with_balances": orgs_with_balances,
            "balance": total_balance_orgs + total_balance_members,
            "stripe": stripe,
            "stripe_balance": stripe_balance,
        },
    )


@login_required()
def stripe_pending(request):
    """Shows any pending stripe transactions.

    Stripe transactions should never really be in a pending state unless
    there is a problem. They go from intent to success usually. The only time
    they will sit in pending is if Stripe is slow to talk to us or there is an
    error.

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """
    if not rbac_user_has_role(request.user, "payments.global.view"):
        return rbac_forbidden(request, "payments.global.view")

    try:
        stripe_latest = StripeTransaction.objects.filter(status="Success").latest(
            "created_date"
        )
        stripe_manual_pending = StripeTransaction.objects.filter(status="Pending")
        stripe_manual_intent = StripeTransaction.objects.filter(
            status="Intent"
        ).order_by("-created_date")[:20]
        stripe_auto_pending = User.objects.filter(stripe_auto_confirmed="Pending")
    except StripeTransaction.DoesNotExist:
        return HttpResponse("No Stripe data found")

    return render(
        request,
        "payments/admin/stripe_pending.html",
        {
            "stripe_manual_pending": stripe_manual_pending,
            "stripe_manual_intent": stripe_manual_intent,
            "stripe_latest": stripe_latest,
            "stripe_auto_pending": stripe_auto_pending,
        },
    )


@login_required()
def admin_members_with_balance(request):
    """Shows any open balances held by members

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """
    if not rbac_user_has_role(request.user, "payments.global.view"):
        return rbac_forbidden(request, "payments.global.view")

    members_list = MemberTransaction.objects.order_by(
        "member", "-created_date"
    ).distinct("member")

    # exclude zeros
    members = []
    for member in members_list:
        if member.balance != 0:
            members.append(member)

    things = cobalt_paginator(request, members)

    return render(
        request, "payments/admin/admin_members_with_balance.html", {"things": things}
    )


@login_required()
def admin_orgs_with_balance(request):
    """Shows any open balances held by orgs

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """
    if not rbac_user_has_role(request.user, "payments.global.view"):
        return rbac_forbidden(request, "payments.global.view")

    orgs_list = OrganisationTransaction.objects.order_by(
        "organisation", "-created_date"
    ).distinct("organisation")

    # exclude zeros
    orgs = []
    for org in orgs_list:
        if org.balance != 0:
            orgs.append(org)

    things = cobalt_paginator(request, orgs)

    return render(
        request, "payments/admin/admin_orgs_with_balance.html", {"things": things}
    )


@login_required()
def admin_members_with_balance_csv(request):
    """Shows any open balances held by members - as CSV

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse - CSV
    """
    if not rbac_user_has_role(request.user, "payments.global.view"):
        return rbac_forbidden(request, "payments.global.view")

    members_list = MemberTransaction.objects.order_by(
        "member", "-created_date"
    ).distinct("member")

    # exclude zeros
    members = []
    for member in members_list:
        if member.balance != 0:
            members.append(member)

    local_dt = timezone.localtime(timezone.now(), TZ)
    today = dateformat.format(local_dt, "Y-m-d H:i:s")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="member-balances.csv"'

    writer = csv.writer(response)
    writer.writerow(
        ["Member Balances", "Downloaded by %s" % request.user.full_name, today]
    )
    writer.writerow(
        ["Member Number", "Member First Name", "Member Last Name", "Balance"]
    )

    for member in members:
        writer.writerow(
            [
                member.member.system_number,
                member.member.first_name,
                member.member.last_name,
                member.balance,
            ]
        )

    return response


@login_required()
def admin_orgs_with_balance_csv(request):
    """Shows any open balances held by orgs - as CSV

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse - CSV
    """
    if not rbac_user_has_role(request.user, "payments.global.view"):
        return rbac_forbidden(request, "payments.global.view")

    orgs_list = OrganisationTransaction.objects.order_by(
        "organisation", "-created_date"
    ).distinct("organisation")

    # exclude zeros
    orgs = []
    for org in orgs_list:
        if org.balance != 0:
            orgs.append(org)

    local_dt = timezone.localtime(timezone.now(), TZ)
    today = dateformat.format(local_dt, "Y-m-d H:i:s")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="organisation-balances.csv"'

    writer = csv.writer(response)
    writer.writerow(
        ["Organisation Balances", "Downloaded by %s" % request.user.full_name, today]
    )
    writer.writerow(["Club Number", "Club Name", "Balance"])

    for org in orgs:
        writer.writerow([org.organisation.org_id, org.organisation.name, org.balance])

    return response


def _admin_view_specific_transactions_csv_download(
    request, filename, title, manual_member, manual_org
):
    """Produce CSV file from the view of specific transaction types

    Args:
        request: Standard request Object
        filename: Name of output file
        title: Title for report
        manual_member: transactions relating to members (can be empty)
        manual_org: transactions relating to orgs (can be empty)

    """

    local_dt = timezone.localtime(timezone.now(), TZ)
    today = dateformat.format(local_dt, "Y-m-d H:i:s")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f"attachment; filename={filename}"

    writer = csv.writer(response)
    writer.writerow(
        [
            title,
            "Downloaded by %s" % request.user.full_name,
            today,
        ]
    )

    # Members
    writer.writerow("")
    writer.writerow(["Member Transactions"])

    writer.writerow(
        [
            "Date",
            "Administrator",
            "Transaction Type",
            f"{GLOBAL_ORG} Number",
            "User",
            "Description",
            "Amount",
        ]
    )

    for member in manual_member:
        local_dt = timezone.localtime(member.created_date, TZ)

        writer.writerow(
            [
                dateformat.format(local_dt, "Y-m-d H:i:s"),
                member.other_member,
                member.type,
                member.member.system_number,
                member.member.full_name,
                member.description,
                member.amount,
            ]
        )

    # Organisations
    writer.writerow("")
    writer.writerow("")
    writer.writerow(["Organisation Transactions"])

    writer.writerow(
        [
            "Date",
            "Administrator",
            "Transaction Type",
            "Club ID",
            "Organisation",
            "Description",
            "Amount",
        ]
    )

    for org in manual_org:
        local_dt = timezone.localtime(org.created_date, TZ)

        writer.writerow(
            [
                dateformat.format(local_dt, "Y-m-d H:i:s"),
                org.member,
                org.type,
                org.organisation.org_id,
                org.organisation,
                org.description,
                org.amount,
            ]
        )

    return response


@login_required()
def admin_view_specific_transactions(request, trans_type):
    """Shows transactions of a specific type. e.g. manual adjustments or settlements

    Args:
        request (HTTPRequest): standard request object
        trans_type (str): which transactions to show

    Returns:
        HTTPResponse (Can be CSV)
    """

    transaction_types = {
        "manual_adjust": "Manual Adjustment",
        "settlement": "Settlement",
    }

    if not rbac_user_has_role(request.user, "payments.global.view"):
        return rbac_forbidden(request, "payments.global.view")

    if trans_type not in transaction_types:
        return HttpResponse(f"Invalid transaction type for this report: {trans_type}")

    form = DateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():

        # Need to make the dates TZ aware
        to_date_form = form.cleaned_data["to_date"]
        from_date_form = form.cleaned_data["from_date"]
        # date -> datetime
        to_date = datetime.datetime.combine(to_date_form, datetime.time(23, 59))
        from_date = datetime.datetime.combine(from_date_form, datetime.time(0, 0))
        # make aware
        to_date = make_aware(to_date, TZ)
        from_date = make_aware(from_date, TZ)

        manual_member = MemberTransaction.objects.filter(
            type=transaction_types[trans_type]
        ).filter(created_date__range=(from_date, to_date))

        manual_org = OrganisationTransaction.objects.filter(
            type=transaction_types[trans_type]
        ).filter(created_date__range=(from_date, to_date))

        if "export" not in request.POST:
            return render(
                request,
                "payments/admin/admin_view_specific_transactions.html",
                {
                    "form": form,
                    "manual_member": manual_member,
                    "manual_org": manual_org,
                    "title": transaction_types[trans_type],
                },
            )

        filename = transaction_types[trans_type].replace(" ", "_") + ".csv"
        return _admin_view_specific_transactions_csv_download(
            request, filename, transaction_types[trans_type], manual_member, manual_org
        )

    return render(
        request,
        "payments/admin/admin_view_specific_transactions.html",
        {"form": form, "title": transaction_types[trans_type]},
    )


@rbac_check_role("payments.global.view")
def admin_view_stripe_transactions(request):
    """Shows stripe transactions for an admin

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse (can be CSV)
    """

    page_no = None

    form = DateForm(request.POST) if request.method == "POST" else DateForm()
    if form.is_valid():

        # Need to make the dates TZ aware
        to_date_form = form.cleaned_data["to_date"]
        from_date_form = form.cleaned_data["from_date"]
        # date -> datetime
        to_date = datetime.datetime.combine(to_date_form, datetime.time(23, 59))
        from_date = datetime.datetime.combine(from_date_form, datetime.time(0, 0))
        # make aware
        to_date = make_aware(to_date, TZ)
        from_date = make_aware(from_date, TZ)

        stripes = (
            StripeTransaction.objects.filter(created_date__range=(from_date, to_date))
            .exclude(stripe_method=None)
            .order_by("-created_date")
        )

        # Go to the first page if this is a new search
        page_no = 1

    else:

        stripes = StripeTransaction.objects.exclude(stripe_method=None).order_by(
            "-created_date"
        )

    # Get payment static
    pay_static = PaymentStatic.objects.filter(active=True).last()
    stripe.api_key = STRIPE_SECRET_KEY

    for stripe_item in stripes:
        stripe_item.amount_settle = (
            float(stripe_item.amount) - float(pay_static.stripe_cost_per_transaction)
        ) * (1.0 - float(pay_static.stripe_percentage_charge) / 100.0)

        # We used to go to Stripe to get the details but it times out even if the list is quite small.

    if "export" in request.POST:

        local_dt = timezone.localtime(timezone.now(), TZ)
        today = dateformat.format(local_dt, "Y-m-d H:i:s")

        response = HttpResponse(content_type="text/csv")
        response[
            "Content-Disposition"
        ] = 'attachment; filename="stripe-transactions.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "Stripe Transactions",
                "Downloaded by %s" % request.user.full_name,
                today,
            ]
        )

        writer.writerow(
            [
                "Date",
                "Status",
                "member",
                "Amount",
                "Refund Amount",
                "Expected Settlement Amount",
                "Description",
                "stripe_reference",
                "stripe_exp_month",
                "stripe_exp_year",
                "stripe_last4",
                "linked_organisation",
                "linked_member",
                "linked_transaction_type",
                "linked_amount",
                "stripe_receipt_url",
            ]
        )

        for stripe_item in stripes:
            local_dt = timezone.localtime(stripe_item.created_date, TZ)

            writer.writerow(
                [
                    dateformat.format(local_dt, "Y-m-d H:i:s"),
                    stripe_item.status,
                    stripe_item.member,
                    stripe_item.amount,
                    stripe_item.refund_amount,
                    stripe_item.amount_settle,
                    stripe_item.description,
                    stripe_item.stripe_reference,
                    stripe_item.stripe_exp_month,
                    stripe_item.stripe_exp_year,
                    stripe_item.stripe_last4,
                    stripe_item.linked_organisation,
                    stripe_item.linked_member,
                    stripe_item.linked_transaction_type,
                    stripe_item.linked_amount,
                    stripe_item.stripe_receipt_url,
                ]
            )
        return response

    else:
        things = cobalt_paginator(request, stripes, page_no=page_no)
        return render(
            request,
            "payments/admin/admin_view_stripe_transactions.html",
            {"form": form, "things": things},
        )


@rbac_check_role("payments.global.view")
def admin_view_stripe_transaction_detail(request, stripe_transaction_id):
    """Shows stripe transaction details for an admin

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    stripe_item = get_object_or_404(StripeTransaction, pk=stripe_transaction_id)

    payment_static = PaymentStatic.objects.filter(active="True").last()

    if not payment_static:
        return HttpResponse("<h1>Payment Static has not been set up</h1>")

    stripe.api_key = STRIPE_SECRET_KEY
    if stripe_item.stripe_balance_transaction:

        balance_tran = stripe.BalanceTransaction.retrieve(
            stripe_item.stripe_balance_transaction
        )
        stripe_item.stripe_fees = balance_tran.fee / 100.0
        stripe_item.stripe_fee_details = balance_tran.fee_details
        for row in stripe_item.stripe_fee_details:
            row.amount = row.amount / 100.0
        stripe_item.stripe_settlement = balance_tran.net / 100.0
        stripe_item.stripe_created_date = datetime.datetime.fromtimestamp(
            balance_tran.created
        )
        stripe_item.stripe_available_on = datetime.datetime.fromtimestamp(
            balance_tran.available_on
        )
        stripe_item.stripe_percentage_charge = (
            100.0
            * (float(stripe_item.amount) - float(stripe_item.stripe_settlement))
            / float(stripe_item.amount)
        )
        our_estimate_fee = float(stripe_item.amount) * float(
            payment_static.stripe_percentage_charge
        ) / 100.0 + float(payment_static.stripe_cost_per_transaction)
        our_estimate_fee_percent = our_estimate_fee * 100.0 / float(stripe_item.amount)
        stripe_item.our_estimate_fee = "%.2f" % our_estimate_fee
        stripe_item.our_estimate_fee_percent = "%.2f" % our_estimate_fee_percent
    return render(
        request,
        "payments/admin/admin_view_stripe_transaction_detail.html",
        {"stripe_item": stripe_item},
    )


@rbac_check_role("payments.global.edit")
def admin_refund_stripe_transaction(request, stripe_transaction_id):
    """Allows an Admin to refund a Stripe transaction

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    stripe_item = get_object_or_404(StripeTransaction, pk=stripe_transaction_id)

    if stripe_item.member == request.user:
        messages.error(
            request,
            "You cannot refund your own transactions. Do it through Stripe, their security isn't as good as ours.",
            extra_tags="cobalt-message-error",
        )
        return redirect("payments:admin_view_stripe_transactions")

    # Calculate how much refund is left
    stripe_item.refund_left = stripe_item.amount - stripe_item.refund_amount

    member_balance = get_balance(stripe_item.member)

    if request.method == "POST":

        form = StripeRefund(request.POST, payment_amount=stripe_item.refund_left)
        if form.is_valid():

            # Check if this the first entry screen or the confirmation screen
            if "first-submit" in request.POST:
                # First screen so show user the confirm
                after_balance = float(member_balance) - float(
                    form.cleaned_data["amount"]
                )
                return render(
                    request,
                    "payments/admin/admin_refund_stripe_transaction_confirm.html",
                    {
                        "stripe_item": stripe_item,
                        "form": form,
                        "after_balance": after_balance,
                    },
                )

            elif "confirm-submit" in request.POST:
                # Confirm screen so make refund

                amount = form.cleaned_data["amount"]
                description = form.cleaned_data["description"]

                # Stripe uses cents not dollars
                stripe_amount = int(amount * 100)

                stripe.api_key = STRIPE_SECRET_KEY

                try:
                    rc = stripe.Refund.create(
                        charge=stripe_item.stripe_reference,
                        amount=stripe_amount,
                    )

                except stripe.error.InvalidRequestError as e:
                    log_event(
                        user=request.user.full_name,
                        severity="CRITICAL",
                        source="Payments",
                        sub_source="Admin refund",
                        message=str(e),
                    )

                    return render(
                        request,
                        "payments/admin/payments_refund_error.html",
                        {"rc": e, "stripe_item": stripe_item},
                    )

                if rc["status"] not in ["succeeded", "pending"]:
                    log_event(
                        user=request.user.full_name,
                        severity="CRITICAL",
                        source="Payments",
                        sub_source="Admin refund",
                        message=f"Admin Refund. Unknown status from stripe refund. Stripe Item:{stripe_item}    Return Code{rc}",
                    )
                    return render(
                        request,
                        "payments/admin/payments_refund_error.html",
                        {"rc": rc, "stripe_item": stripe_item},
                    )

                # Call atomic database update
                refund_stripe_transaction_sub(
                    stripe_item, amount, description, counterparty=request.user
                )

                # Notify member
                email_body = f"""<b>{request.user.full_name}</b> has refunded {GLOBAL_CURRENCY_SYMBOL}{amount:.2f}
                 to your card.<br><br>
                 The description was: {description}<br><br>
                 Please note that It can take up to two weeks for the money to appear in your card statement.<br><br>
                 Your {BRIDGE_CREDITS} account balance has been reduced to reflect this refund.<br><br>
                 You can view your statement by clicking on the link below<br><br>
                 """
                context = {
                    "name": stripe_item.member.first_name,
                    "title": "Card Refund",
                    "email_body": email_body,
                    "host": COBALT_HOSTNAME,
                    "link": "/payments",
                    "link_text": "View Statement",
                }

                html_msg = render_to_string(
                    "notifications/email_with_button.html", context
                )

                # send
                contact_member(
                    member=stripe_item.member,
                    msg="Card Refund - %s%s" % (GLOBAL_CURRENCY_SYMBOL, amount),
                    contact_type="Email",
                    html_msg=html_msg,
                    link="/payments",
                    subject="Card Refund",
                )

                log_event(
                    user=stripe_item.member,
                    severity="INFO",
                    source="Payments",
                    sub_source="Admin refund",
                    message=f"{request.user} refunded {GLOBAL_CURRENCY_SYMBOL}{amount} to {stripe_item.member.full_name}",
                )

                msg = f"Refund Successful. Paid {GLOBAL_CURRENCY_SYMBOL}{amount} to {stripe_item.member}"
                messages.success(request, msg, extra_tags="cobalt-message-success")
                return redirect("payments:admin_view_stripe_transactions")

    else:
        form = StripeRefund(payment_amount=stripe_item.refund_left)
        form.fields["amount"].initial = stripe_item.refund_left
        form.fields["description"].initial = "Card Refund"

    return render(
        request,
        "payments/admin/admin_refund_stripe_transaction.html",
        {"stripe_item": stripe_item, "form": form, "member_balance": member_balance},
    )


@atomic
def refund_stripe_transaction_sub(stripe_item, amount, description, counterparty=None):
    """Atomic transaction update for refunds"""

    # Update the Stripe transaction
    if amount + stripe_item.refund_amount >= stripe_item.amount:
        stripe_item.status = "Refunded"
    else:
        stripe_item.status = "Partial refund"

    stripe_item.refund_amount += amount

    stripe_item.save()

    # Create a new transaction for the user
    balance = get_balance(stripe_item.member) - float(amount)

    abf = get_object_or_404(Organisation, pk=GLOBAL_ORG_ID)

    act = MemberTransaction()
    act.member = stripe_item.member
    act.amount = -amount
    # Linking to the stripe transaction messes up the statements
    # act.stripe_transaction = stripe_item
    act.balance = balance
    act.description = description
    act.organisation = abf
    act.type = "Card Refund"

    act.save()

    log_event(
        user=stripe_item.member.full_name,
        severity="INFO",
        source="Payments",
        sub_source="Card Refund",
        message=description,
    )


@rbac_check_role("payments.global.edit")
def admin_payments_static(request):
    """Manage static data for payments

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    payment_static = PaymentStatic.objects.filter(active=True).last()

    if payment_static:
        form = PaymentStaticForm(instance=payment_static)
    else:
        form = PaymentStaticForm()

    if request.method == "POST":
        form = PaymentStaticForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.modified_by = request.user
            obj.save()

            # set all others to be inactive
            PaymentStatic.objects.all().update(active=False)

            # set this one active
            payment_static = PaymentStatic.objects.order_by("id").last()
            payment_static.active = True
            payment_static.save()

            messages.success(
                request, "Settings updated", extra_tags="cobalt-message-success"
            )
            return redirect("payments:statement_admin_summary")

    return render(
        request,
        "payments/admin/admin_payments_static.html",
        {"form": form, "payment_static_old": payment_static},
    )


@login_required()
def admin_payments_static_history(request):
    """history for static data for payments

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    if not rbac_user_has_role(request.user, "payments.global.edit"):
        return rbac_forbidden(request, "payments.global.edit")

    payment_statics = PaymentStatic.objects.order_by("-created_date")

    return render(
        request,
        "payments/admin/admin_payments_static_history.html",
        {"payment_statics": payment_statics},
    )


@login_required()
def admin_payments_static_org_override(request):
    """Manage static data for individual orgs (override default values)

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    if not rbac_user_has_role(request.user, "payments.global.edit"):
        return rbac_forbidden(request, "payments.global.edit")

    org_statics = OrganisationSettlementFees.objects.all()

    return render(
        request,
        "payments/admin/admin_payments_static_org_override.html",
        {"org_statics": org_statics},
    )


@login_required()
def admin_payments_static_org_override_add(request):
    """Manage static data for individual orgs (override default values)
    This screen adds an override

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    if not rbac_user_has_role(request.user, "payments.global.edit"):
        return rbac_forbidden(request, "payments.global.edit")

    form = OrgStaticOverrideForm(request.POST or None)

    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(
                request, "Entry added", extra_tags="cobalt-message-success"
            )
            return redirect("payments:admin_payments_static_org_override")
        else:
            messages.error(request, form.errors, extra_tags="cobalt-message-error")

    return render(
        request,
        "payments/admin/admin_payments_static_org_override_add.html",
        {"form": form},
    )


@rbac_check_role("payments.global.edit")
def admin_payments_static_org_override_delete(request, item_id):
    """Manage static data for individual orgs (override default values)
    This screen deletes an override

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    item = get_object_or_404(OrganisationSettlementFees, pk=item_id)

    item.delete()

    messages.success(request, "Entry deleted", extra_tags="cobalt-message-success")
    return redirect("payments:admin_payments_static_org_override")


@rbac_check_role("payments.global.edit")
def admin_player_payments(request, member_id):
    """Manage a players payments as an admin. E.g. make a refund to a credit card.

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    member = get_object_or_404(User, pk=member_id)
    summary = user_summary(member.system_number)
    balance = get_balance(member)

    stripes = StripeTransaction.objects.filter(member=member).order_by("-created_date")[
        :10
    ]

    return render(
        request,
        "payments/admin/admin_player_payments.html",
        {"profile": member, "summary": summary, "balance": balance, "stripes": stripes},
    )


def _get_member_balance_at_date(ref_date):
    """Internal function to get list of members with balances at specific date"""

    # # get latest transaction per member - can't do a Sum after a distinct - not yet supported
    # members = (
    #     MemberTransaction.objects.filter(created_date__lt=ref_date)
    #     .order_by("member", "-created_date")
    #     .distinct("member")
    #     .exclude(balance=0.0)
    # )

    member_balances = (
        MemberTransaction.objects.filter(created_date__lt=ref_date)
        .values(
            "member",
            "member__first_name",
            "member__last_name",
            "member__system_number",
            "balance",
        )
        .distinct("member")
        .order_by("member", "-id")
    )

    member_total_balance = 0.0

    for member_balance in member_balances:
        member_total_balance += float(member_balance["balance"])

    return member_total_balance, member_balances


def _get_org_balance_at_date(ref_date):
    """Internal function to get list of organisations with balances at specific date"""

    # # get summary per organisation
    # org_trans = (
    #     OrganisationTransaction.objects.filter(created_date__lt=ref_date)
    #     .values('organisation', "organisation__name", "type")
    #     .order_by("organisation", "type")
    #     .annotate(sub_amount=Sum('amount'))
    # )
    #
    # print(org_trans)
    # for org in org_trans:
    #     print(org)

    org_balances = (
        OrganisationTransaction.objects.filter(created_date__lt=ref_date)
        .values("organisation", "organisation__name", "organisation__org_id", "balance")
        .distinct("organisation")
        .order_by("organisation", "-id")
    )

    print(org_balances)

    # Better to calculate total in Python as we already have the data loaded
    org_total_balance = 0.0
    for org_balance in org_balances:
        org_total_balance += float(org_balance["balance"])

    return org_total_balance, org_balances


@rbac_check_role("payments.global.view")
def admin_stripe_rec(request):
    """This will become the Stripe reconciliation. For now it just shows the balances to allow a manual reconciliation

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """
    ref_date, _ = _admin_stripe_rec_ref_date(request)

    members_balance, members = _get_member_balance_at_date(ref_date)
    orgs_balance, orgs = _get_org_balance_at_date(ref_date)

    return render(
        request,
        "payments/admin/stripe_rec.html",
        {
            "members_balance": members_balance,
            "orgs_balance": orgs_balance,
            "ref_date": ref_date,
            "members_count": members.count(),
            "orgs_count": orgs.count(),
        },
    )


def _admin_stripe_rec_ref_date(request):
    """common function to handle reference date"""

    # Default date is last day of the previous month. Get first of this month and step back 1 day
    ref_date = datetime.datetime.now(tz=TZ).replace(
        day=1, hour=23, minute=59, second=59, microsecond=999_999
    ) - datetime.timedelta(days=1)

    form_date = request.POST.get("ref_date")

    if form_date:
        ref_date = (
            datetime.datetime.strptime(form_date, "%d/%m/%Y")
            .replace(tzinfo=TZ)
            .replace(hour=23, minute=59, second=59, microsecond=999_999)
        )

    # also calculate date a month earlier
    ref_date_month_earlier = ref_date.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    ) - datetime.timedelta(days=1)

    return ref_date, ref_date_month_earlier


@rbac_check_role("payments.global.view")
def admin_stripe_rec_download(request):
    """CSV download of all movements for the month prior to the reference date
    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    # Get the ref date
    ref_date, ref_date_month_earlier = _admin_stripe_rec_ref_date(request)

    # Get the 3 different kinds of financial transaction
    members = MemberTransaction.objects.filter(created_date__lte=ref_date).filter(
        created_date__gte=ref_date_month_earlier
    )
    stripes = (
        StripeTransaction.objects.filter(created_date__lte=ref_date)
        .filter(created_date__gte=ref_date_month_earlier)
        .filter(status__in=["Succeeded", "Partial refund", "Refunded"])
    )
    orgs = OrganisationTransaction.objects.filter(created_date__lte=ref_date).filter(
        created_date__gte=ref_date_month_earlier
    )

    # Merge them together
    results = []

    # MemberTransactions
    for member in members:
        counterparty = ""
        if member.other_member:
            counterparty = member.other_member
        if member.organisation:
            counterparty = member.organisation
        item = {
            "table": "Member Transaction",
            "created_date": member.created_date,
            "counterparty": counterparty,
            "reference_no": member.reference_no,
            "type": member.type,
            "description": member.description,
            "amount": member.amount,
            "balance": member.balance,
        }
        results.append(item)

    # OrgTransactions
    for org in orgs:
        counterparty = ""
        if org.member:
            counterparty = org.member
        item = {
            "table": "Organisation Transaction",
            "created_date": org.created_date,
            "counterparty": counterparty,
            "reference_no": org.reference_no,
            "type": org.type,
            "description": org.description,
            "amount": org.amount,
            "balance": org.balance,
        }
        results.append(item)

    # StripeTransactions
    for stripe_item in stripes:
        counterparty = ""
        if stripe_item.linked_member:
            counterparty = stripe_item.linked_member
        if stripe_item.linked_organisation:
            counterparty = stripe_item.linked_organisation
        item = {
            "table": "Stripe Transaction",
            "created_date": stripe_item.created_date,
            "counterparty": counterparty,
            "reference_no": stripe_item.stripe_reference,
            "type": stripe_item.status,
            "description": stripe_item.description,
            "amount": stripe_item.amount,
            "balance": "",
        }
        results.append(item)

    # Sort by created_date
    results = sorted(results, key=lambda k: k["created_date"])

    local_dt = timezone.localtime(timezone.now(), TZ)
    today = dateformat.format(local_dt, "Y-m-d H:i:s")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="reconciliation.csv"'

    writer = csv.writer(response)
    writer.writerow([f"Generated by {request.user.full_name}", f"Generated on {today}"])
    writer.writerow(
        ["Date range >=", dateformat.format(ref_date_month_earlier, "Y-m-d H:i:s")]
    )
    writer.writerow(["Date range <=", dateformat.format(ref_date, "Y-m-d H:i:s")])
    writer.writerow([""])
    writer.writerow(
        [
            "Date",
            "Table",
            "Counterparty",
            "Reference",
            "Type",
            "Description",
            "Amount",
            "Balance",
        ]
    )

    for result in results:
        writer.writerow(
            [
                dateformat.format(result["created_date"], "Y-m-d H:i:s"),
                result["table"],
                result["counterparty"],
                result["reference_no"],
                result["type"],
                result["description"],
                result["amount"],
                result["balance"],
            ]
        )

    return response


@rbac_check_role("payments.global.view")
def admin_stripe_rec_download_member(request):
    """CSV download of closing member balances just prior to the reference date
    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    # Get the ref date
    ref_date, _ = _admin_stripe_rec_ref_date(request)

    # Get the member balances
    members_balance, members = _get_member_balance_at_date(ref_date)

    local_dt = timezone.localtime(timezone.now(), TZ)
    today = dateformat.format(local_dt, "Y-m-d H:i:s")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="member_balances.csv"'

    writer = csv.writer(response)
    writer.writerow([f"Generated by {request.user.full_name}", f"Generated on {today}"])
    writer.writerow(["Balances prior to", dateformat.format(ref_date, "Y-m-d H:i:s")])

    writer.writerow([""])
    writer.writerow(
        [
            f"{GLOBAL_ORG} Number",
            "First Name",
            "Last Name",
            "Balance",
        ]
    )

    for member in members:
        writer.writerow(
            [
                member["member__system_number"],
                member["member__first_name"],
                member["member__last_name"],
                member["balance"],
            ]
        )

    return response


@rbac_check_role("payments.global.view")
def admin_stripe_rec_download_org(request):
    """CSV download of closing organisation balances just prior to the reference date
    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    # Get the ref date
    ref_date, _ = _admin_stripe_rec_ref_date(request)

    # Get the member balances
    org_balance, orgs = _get_org_balance_at_date(ref_date)

    local_dt = timezone.localtime(timezone.now(), TZ)
    today = dateformat.format(local_dt, "Y-m-d H:i:s")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="organisation_balances.csv"'

    writer = csv.writer(response)
    writer.writerow([f"Generated by {request.user.full_name}", f"Generated on {today}"])
    writer.writerow(["Balances prior to", dateformat.format(ref_date, "Y-m-d H:i:s")])

    writer.writerow([""])
    writer.writerow(
        [
            "Organisation",
            f"{GLOBAL_ORG} Org Number",
            "Balance",
        ]
    )

    for org in orgs:
        writer.writerow(
            [
                org["organisation__name"],
                org["organisation__org_id"],
                org["balance"],
            ]
        )

    return response


@login_required()
@transaction.atomic
def settlement(request):
    """process payments to organisations. This is expected to be a monthly
        activity.

    At certain points in time an administrator will clear out the balances of
    the organisations accounts and transfer actual money to them through the
    banking system. This is not currently possible to do electronically so this
    is a manual process.

    The administrator should use this list to match with the bank transactions and
    then confirm through this view that the payments have been made.

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """
    if not rbac_user_has_role(request.user, "payments.global.edit"):
        return rbac_forbidden(request, "payments.global.edit")

    payment_static = PaymentStatic.objects.filter(active="True").last()

    if not payment_static:
        return HttpResponse("<h1>Payment Static has not been set up</h1>")

    # orgs with outstanding balances
    # Django is a bit too clever here so we actually have to include balance=0.0 and filter
    # it in the code, otherwise we get the most recent non-zero balance. There may be
    # a way to do this but I couldn't figure it out.
    orgs = OrganisationTransaction.objects.order_by(
        "organisation", "-created_date"
    ).distinct("organisation")
    org_list = []

    non_zero_orgs = []
    for org in orgs:
        print(org.id)
        if org.balance != 0.0:
            org_list.append((org.id, org.organisation.name))
            non_zero_orgs.append(org)

    if request.method == "POST":

        form = SettlementForm(request.POST, orgs=org_list)
        if form.is_valid():

            # load balances - Important! Do not get the current balance for an
            # org as this may have changed. Use the list confirmed by the user.
            settlement_ids = form.cleaned_data["settle_list"]
            settlements = OrganisationTransaction.objects.filter(pk__in=settlement_ids)

            if "export" in request.POST:  # CSV download

                local_dt = timezone.localtime(timezone.now(), TZ)
                today = dateformat.format(local_dt, "Y-m-d H:i:s")

                response = HttpResponse(content_type="text/csv")
                response[
                    "Content-Disposition"
                ] = 'attachment; filename="settlements.csv"'

                writer = csv.writer(response)
                writer.writerow(
                    [
                        "Settlements Export",
                        "Downloaded by %s" % request.user.full_name,
                        today,
                    ]
                )
                writer.writerow(
                    [
                        "CLub Number",
                        "CLub Name",
                        "BSB",
                        "Account Number",
                        "Gross Amount",
                        f"{GLOBAL_ORG} fees %",
                        "Settlement Amount",
                    ]
                )

                for org in settlements:
                    writer.writerow(
                        [
                            org.organisation.org_id,
                            org.organisation.name,
                            org.organisation.bank_bsb,
                            org.organisation.bank_account,
                            org.balance,
                            org.organisation.settlement_fee_percent,
                            org.settlement_amount,
                        ]
                    )

                return response

            else:  # confirm payments

                trans_list = []
                total = 0.0

                system_org = get_object_or_404(Organisation, pk=GLOBAL_ORG_ID)

                # Remove money from org accounts
                for item in settlements:
                    total += float(item.balance)
                    trans = update_organisation(
                        organisation=item.organisation,
                        other_organisation=system_org,
                        amount=-item.balance,
                        description=f"Settlement from {GLOBAL_ORG}. Fees {item.organisation.settlement_fee_percent}%. Net Bank Transfer: {GLOBAL_CURRENCY_SYMBOL}{item.settlement_amount}.",
                        log_msg=f"Settlement from {GLOBAL_ORG} to {item.organisation}",
                        source="payments",
                        sub_source="settlements",
                        payment_type="Settlement",
                        bank_settlement_amount=item.settlement_amount,
                    )
                    trans_list.append(trans)

                messages.success(
                    request,
                    "Settlement processed successfully.",
                    extra_tags="cobalt-message-success",
                )
                return render(
                    request,
                    "payments/admin/settlement-complete.html",
                    {"trans": trans_list, "total": total},
                )

    else:
        form = SettlementForm(orgs=org_list)

    return render(
        request, "payments/admin/settlement.html", {"orgs": non_zero_orgs, "form": form}
    )


@login_required()
def manual_adjust_member(request):
    """make a manual adjustment on a member account

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """
    if not rbac_user_has_role(request.user, "payments.global.edit"):
        return rbac_forbidden(request, "payments.global.edit")

    if request.method == "POST":
        form = AdjustMemberForm(request.POST)
        if form.is_valid():
            member = form.cleaned_data["member"]
            amount = form.cleaned_data["amount"]
            description = form.cleaned_data["description"]
            update_account(
                member=member,
                amount=amount,
                description=description,
                log_msg="Manual adjustment by %s %s %s"
                % (request.user, member, amount),
                source="payments",
                sub_source="manual_adjust_member",
                payment_type="Manual Adjustment",
                other_member=request.user,
            )
            msg = "Manual adjustment successful. %s adjusted by %s%s" % (
                member,
                GLOBAL_CURRENCY_SYMBOL,
                amount,
            )
            messages.success(request, msg, extra_tags="cobalt-message-success")
            return redirect("payments:statement_admin_summary")

    else:
        form = AdjustMemberForm()

        return render(
            request, "payments/admin/manual_adjust_member.html", {"form": form}
        )


@login_required()
def manual_adjust_org(request, org_id=None, default_transaction=None):
    """make a manual adjustment on an organisation account

    Args:
        request (HTTPRequest): standard request object
        org_id: optional id of organisation
        default_transaction: Allows a default for transaction type to be selected

    Returns:
        HTTPResponse
    """
    if not rbac_user_has_role(request.user, "payments.global.edit"):
        return rbac_forbidden(request, "payments.global.edit")

    # TODO: move this to model as an enum
    payment_type_dic = {1: "Manual Adjustment", 2: "Settlement"}

    form = AdjustOrgForm(request.POST or None, default_transaction=default_transaction)

    if form.is_valid():
        org = form.cleaned_data["organisation"]
        amount = form.cleaned_data["amount"]
        bank_settlement_amount = -float(amount) * (
            1.0 - float(org.settlement_fee_percent) / 100.0
        )
        description = form.cleaned_data["description"]
        adjustment_type = int(form.cleaned_data["adjustment_type"])
        payment_type = payment_type_dic[adjustment_type]
        update_organisation(
            organisation=org,
            amount=amount,
            description=description,
            log_msg=description,
            source="payments",
            sub_source="manual_adjustment_org",
            payment_type=payment_type,
            member=request.user,
            bank_settlement_amount=bank_settlement_amount,
        )
        msg = "Adjustment successful. %s adjusted by %s%s" % (
            org,
            GLOBAL_CURRENCY_SYMBOL,
            amount,
        )
        messages.success(request, msg, extra_tags="cobalt-message-success")
        return redirect("payments:statement_admin_summary")
    else:
        print(form.errors)

    org = get_object_or_404(Organisation, pk=org_id) if org_id else None
    return render(
        request, "payments/admin/manual_adjust_org.html", {"form": form, "org": org}
    )
