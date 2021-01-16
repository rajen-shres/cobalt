# -*- coding: utf-8 -*-
"""Handles all activities associated with payments that talk to users.

This module handles all of the functions that interact directly with
a user. i.e. they generally accept a ``Request`` and return an
``HttpResponse``.
See also `Payments Core`_. This handles the other side of the interactions.
They both work together.

Key Points:
    - Payments is a service module, it is requested to do things on behalf of
      another module and does not know why it is doing them.
    - Payments are often not real time, for manual payments, the user will
      be taken to another screen that interacts directly with Stripe, and for
      automatic top up payments, the top up may fail and require user input.
    - The asynchronous nature of payments makes it more complex than many of
      the Cobalt modules so the documentation needs to be of a higher standard.
      See `Payments Overview`_ for more details.

.. _Payments Core:
   #module-payments.core

.. _Payments Overview:
   ./payments_overview.html

"""

import csv
import datetime
import requests
import stripe
import pytz
import json
from django.utils import timezone, dateformat
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, Http404
from django.db.models import Sum
from django.db import transaction
from django.contrib import messages
from notifications.views import contact_member
from logs.views import log_event
from cobalt.settings import (
    STRIPE_SECRET_KEY,
    GLOBAL_MPSERVER,
    AUTO_TOP_UP_LOW_LIMIT,
    AUTO_TOP_UP_MAX_AMT,
    AUTO_TOP_UP_DEFAULT_AMT,
    GLOBAL_ORG,
    GLOBAL_ORG_ID,
    GLOBAL_CURRENCY_SYMBOL,
    GLOBAL_CURRENCY_NAME,
    BRIDGE_CREDITS,
    TIME_ZONE,
    COBALT_HOSTNAME,
)
from .forms import (
    TestTransaction,
    MemberTransfer,
    MemberTransferOrg,
    ManualTopup,
    SettlementForm,
    AdjustMemberForm,
    AdjustOrgForm,
    DateForm,
    PaymentStaticForm,
    OrgStaticOverrideForm,
)
from .core import (
    payment_api,
    get_balance,
    auto_topup_member,
    update_organisation,
    update_account,
)
from organisations.views import org_balance
from .models import (
    MemberTransaction,
    StripeTransaction,
    OrganisationTransaction,
    PaymentStatic,
    OrganisationSettlementFees,
)
from accounts.models import User, TeamMate
from utils.utils import cobalt_paginator
from organisations.models import Organisation
from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden
from django.utils.timezone import make_aware

TZ = pytz.timezone(TIME_ZONE)


# @login_required()
# #################################
# # test_payment                  #
# #################################
# def test_payment(request):
#     """This is a temporary view that can be used to test making a payment against
#     a members account. This simulates them entering an event or paying a subscription."""
#
#     if request.method == "POST":
#         form = TestTransaction(request.POST)
#         if form.is_valid():
#             description = form.cleaned_data["description"]
#             amount = form.cleaned_data["amount"]
#             member = request.user
#             organisation = form.cleaned_data["organisation"]
#             url = form.cleaned_data["url"]
#             payment_type = form.cleaned_data["type"]
#
#             return payment_api(
#                 request=request,
#                 description=description,
#                 amount=amount,
#                 member=member,
#                 route_code="MAN",
#                 route_payload=None,
#                 organisation=organisation,
#                 log_msg=None,
#                 payment_type=payment_type,
#                 url=url,
#             )
#     else:
#         form = TestTransaction()
#
#     if request.user.auto_amount:
#         auto_amount = request.user.auto_amount
#     else:
#         auto_amount = None
#
#     balance = get_balance(request.user)
#
#     return render(
#         request,
#         "payments/test_payment.html",
#         {
#             "form": form,
#             "auto_amount": auto_amount,
#             "balance": balance,
#             "lowbalance": AUTO_TOP_UP_LOW_LIMIT,
#         },
#     )


####################
# statement_common #
####################
def statement_common(user):
    """Member statement view - common part across online, pdf and csv

    Handles the non-formatting parts of statements.

    Args:
        user (User): standard user object

    Returns:
        5-element tuple containing
            - **summary** (*dict*): Basic info about user from MasterPoints
            - **club** (*str*): Home club name
            - **balance** (*float* or *str*): Users account balance
            - **auto_button** (*bool*): status of auto top up
            - **events_list** (*list*): list of MemberTransactions

    """

    # Get summary data
    qry = "%s/mps/%s" % (GLOBAL_MPSERVER, user.system_number)
    try:
        summary = requests.get(qry).json()[0]
    except IndexError:  # server down or some error
        # raise Http404
        summary = {}
        summary["IsActive"] = False
        summary["HomeClubID"] = 0

    # Set active to a boolean
    if summary["IsActive"] == "Y":
        summary["IsActive"] = True
    else:
        summary["IsActive"] = False

    # Get home club name
    qry = "%s/club/%s" % (GLOBAL_MPSERVER, summary["HomeClubID"])
    try:
        club = requests.get(qry).json()[0]["ClubName"]
    except IndexError:  # server down or some error
        club = "Unknown"

    # get balance
    last_tran = MemberTransaction.objects.filter(member=user).last()
    if last_tran:
        balance = last_tran.balance
    else:
        balance = "Nil"

    # get auto top up
    if user.stripe_auto_confirmed == "On":
        auto_button = True
    else:
        auto_button = False

    events_list = MemberTransaction.objects.filter(member=user).order_by(
        "-created_date"
    )

    return (summary, club, balance, auto_button, events_list)


#####################
# statement         #
#####################
@login_required()
def statement(request):
    """Member statement view.

    Basic view of statement showing transactions in a web page.

    Args:
        request - standard request object

    Returns:
        HTTPResponse

    """
    (summary, club, balance, auto_button, events_list) = statement_common(request.user)

    things = cobalt_paginator(request, events_list)

    return render(
        request,
        "payments/statement.html",
        {
            "things": things,
            "user": request.user,
            "summary": summary,
            "club": club,
            "balance": balance,
            "auto_button": auto_button,
            "auto_amount": request.user.auto_amount,
        },
    )


################################
# statement_admin_view         #
################################
@login_required()
def statement_admin_view(request, member_id):
    """Member statement view for administrators.

    Basic view of statement showing transactions in a web page. Used by an
    administrator to view a members statement

    Args:
        request - standard request object

    Returns:
        HTTPResponse

    """

    # check access
    role = "payments.global.view"
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    user = get_object_or_404(User, pk=member_id)
    (summary, club, balance, auto_button, events_list) = statement_common(user)

    things = cobalt_paginator(request, events_list, 30)

    return render(
        request,
        "payments/statement.html",
        {
            "things": things,
            "user": user,
            "summary": summary,
            "club": club,
            "balance": balance,
            "auto_button": auto_button,
            "auto_amount": user.auto_amount,
            "admin_view": True,
        },
    )


#####################
# statement_org     #
#####################
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

    if not rbac_user_has_role(request.user, "payments.manage.%s.view" % org_id):
        if not rbac_user_has_role(request.user, "payments.global.view"):
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
        total = total + float(item["total"])

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
        "payments/statement_org.html",
        {
            "things": things,
            "balance": balance,
            "org": organisation,
            "summary": summary,
            "total": total,
            "page_balance": page_balance,
        },
    )


#########################
# statement_csv_org     #
#########################
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

        if not rbac_user_has_role(request.user, "payments.manage.%s.view" % org_id):
            if not rbac_user_has_role(request.user, "payments.global.view"):
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
        total = total + float(item["total"])

    return render(
        request,
        "payments/statement_org_summary_ajax.html",
        {"summary": summary, "total": total},
    )


#####################
# statement_csv     #
#####################
@login_required()
def statement_csv(request, member_id=None):
    """Member statement view - csv download

    Generates a CSV of the statement.

    Args:
        request (HTTPRequest): standard request object
        member_id(int): id of member to view, defaults to logged in user

    Returns:
        HTTPResponse: CSV headed response with CSV statement data

    """

    if member_id:
        if not rbac_user_has_role(request.user, "payments.global.view"):
            return rbac_forbidden(request, "payments.global.view")
        member = get_object_or_404(User, pk=member_id)
    else:
        member = request.user

    (summary, club, balance, auto_button, events_list) = statement_common(member)

    local_dt = timezone.localtime(timezone.now(), TZ)
    today = dateformat.format(local_dt, "Y-m-d H:i:s")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="statement.csv"'

    writer = csv.writer(response)
    writer.writerow([member.full_name, member.system_number, today])
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
        if row.other_member:
            counterparty = row.other_member
        if row.organisation:
            counterparty = row.organisation
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


#####################
# statement_pdf     #
#####################
@login_required()
def statement_pdf(request):
    """Member statement view - csv download

    Generates a PDF of the statement.

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse: PDF headed response with PDF statement data


    """
    #    (summary, club, balance, auto_button, events_list) = statement_common(
    #        request
    #    )  # pylint: disable=unused-variable

    #    today = datetime.today().strftime("%-d %B %Y")

    # return render_to_pdf_response(
    #     request,
    #     "payments/statement_pdf.html",
    #     {
    #         "events": events_list,
    #         "user": request.user,
    #         "summary": summary,
    #         "club": club,
    #         "balance": balance,
    #         "today": today,
    #     },
    # )

    return


############################
# Stripe_create_customer   #
############################
@login_required()
def stripe_create_customer(request):
    """calls Stripe to register a customer.

    Creates a new customer entry with Stripe and sets this member's
    stripe_customer_id to match the customer created. Also sets the
    auto_amount for the member to the system default.

    Args:
        request (HTTPRequest): standard request object

    Returns:
        Nothing.
    """

    stripe.api_key = STRIPE_SECRET_KEY
    customer = stripe.Customer.create(
        name=request.user,
        email=request.user.email,
        metadata={"cobalt_tran_type": "Auto"},
    )
    request.user.stripe_customer_id = customer.id
    request.user.auto_amount = AUTO_TOP_UP_DEFAULT_AMT
    request.user.save()


#######################
# setup_autotopup     #
#######################
@login_required()
def setup_autotopup(request):
    """view to sign up to auto top up.

    Creates Stripe customer if not already defined.
    Hands over to Stripe to process card.

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse: Our page with Stripe code embedded.

    """
    stripe.api_key = STRIPE_SECRET_KEY
    warn = ""

    # Already set up?
    if request.user.stripe_auto_confirmed == "On":
        try:
            paylist = stripe.PaymentMethod.list(
                customer=request.user.stripe_customer_id,
                type="card",
            )
        except stripe.error.InvalidRequestError as error:
            log_event(
                user=request.user.full_name,
                severity="HIGH",
                source="Payments",
                sub_source="setup_autotopup",
                message="Stripe InvalidRequestError: %s" % error.error.message,
            )
            stripe_create_customer(request)
            paylist = None

        except stripe.error.RateLimitError:
            log_event(
                user=request.user.full_name,
                severity="HIGH",
                source="Payments",
                sub_source="setup_autotopup",
                message="Stripe RateLimitError",
            )

        except stripe.error.AuthenticationError:
            log_event(
                user=request.user.full_name,
                severity="CRITICAL",
                source="Payments",
                sub_source="setup_autotopup",
                message="Stripe AuthenticationError",
            )

        except stripe.error.APIConnectionError:
            log_event(
                user=request.user.full_name,
                severity="HIGH",
                source="Payments",
                sub_source="setup_autotopup",
                message="Stripe APIConnectionError - likely network problems",
            )

        except stripe.error.StripeError:
            log_event(
                user=request.user.full_name,
                severity="CRITICAL",
                source="Payments",
                sub_source="setup_autotopup",
                message="Stripe generic StripeError",
            )

        if paylist:  # if customer has a card associated
            card = paylist.data[0].card
            card_type = card.brand
            card_exp_month = card.exp_month
            card_exp_year = card.exp_year
            card_last4 = card.last4
            warn = f"Changing card details will override your {card_type} card ending in {card_last4} \
                    with expiry {card_exp_month}/{card_exp_year}"

    else:
        stripe_create_customer(request)

    balance = get_balance(request.user)
    topup = request.user.auto_amount

    return render(
        request,
        "payments/autotopup.html",
        {"warn": warn, "topup": topup, "balance": balance},
    )


#######################
# member_transfer     #
#######################
@login_required()
def member_transfer(request):
    """view to transfer $ to another member

    This view allows a member to transfer money to another member.

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse

    """

    if request.method == "POST":
        form = MemberTransfer(request.POST, user=request.user)
        if form.is_valid():
            return payment_api(
                request=request,
                description=form.cleaned_data["description"],
                amount=form.cleaned_data["amount"],
                member=request.user,
                other_member=form.cleaned_data["transfer_to"],
                payment_type="Member Transfer",
            )
        else:
            print(form.errors)
    else:
        form = MemberTransfer(user=request.user)

    # get balance
    last_tran = MemberTransaction.objects.filter(member=request.user).last()
    if last_tran:
        balance = last_tran.balance
    else:
        balance = "Nil"

    recents = (
        MemberTransaction.objects.filter(member=request.user)
        .exclude(other_member=None)
        .values("other_member")
        .distinct()
    )
    recent_transfer_to = []
    for r in recents:
        member = User.objects.get(pk=r["other_member"])
        recent_transfer_to.append(member)

    team_mates = TeamMate.objects.filter(user=request.user)
    for team_mate in team_mates:
        recent_transfer_to.append(team_mate.team_mate)

    # make unique - convert to set to be unique, then back to list to sort
    recent_transfer_to = list(set(recent_transfer_to))
    recent_transfer_to.sort(key=lambda x: x.first_name)

    return render(
        request,
        "payments/member_transfer.html",
        {"form": form, "recents": recent_transfer_to, "balance": balance},
    )


########################
# update_auto_amount   #
########################
@login_required()
def update_auto_amount(request):
    """Called by the auto top up page when a user changes the amount of the auto top up.

    The auto top up page has Stripe code on it so a standard form won't work
    for this. Instead we use a little Ajax code on the page to handle this.

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse: "Successful"

    """
    if request.method == "GET":
        amount = request.GET["amount"]
        request.user.auto_amount = amount
        request.user.save()

    return HttpResponse("Successful")


###################
# manual_topup    #
###################
@login_required()
def manual_topup(request):
    """Page to allow credit card top up regardless of auto status.

    This page allows a member to add to their account using a credit card,
    they can do this even if they have already set up for auto top up.

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse

    """

    balance = get_balance(request.user)

    if request.method == "POST":
        form = ManualTopup(request.POST, balance=balance)
        if form.is_valid():
            if form.cleaned_data["card_choice"] == "Existing":  # Use Auto
                (return_code, msg) = auto_topup_member(
                    request.user,
                    topup_required=form.cleaned_data["amount"],
                    payment_type="Manual Top Up",
                )
                if return_code:  # success
                    messages.success(request, msg, extra_tags="cobalt-message-success")
                    return redirect("payments:payments")
                else:  # error
                    messages.error(request, msg, extra_tags="cobalt-message-error")
            else:  # Use Manual
                trans = StripeTransaction()
                trans.description = "Manual Top Up"
                trans.amount = form.cleaned_data["amount"]
                trans.member = request.user
                trans.save()
                msg = "Manual Top Up - Checkout"
                return render(
                    request, "payments/checkout.html", {"trans": trans, "msg": msg}
                )
        # else:
        #     print(form.errors)

    else:
        form = ManualTopup(balance=balance)

    return render(
        request,
        "payments/manual_topup.html",
        {
            "form": form,
            "balance": balance,
            "remaining_balance": AUTO_TOP_UP_MAX_AMT - balance,
        },
    )


######################
# cancel_auto_top_up #
######################
@login_required()
def cancel_auto_top_up(request):
    """Cancel auto top up.

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    if request.method == "POST":
        if request.POST.get("stop_auto"):
            request.user.auto_amount = None
            request.user.stripe_auto_confirmed = "Off"
            request.user.stripe_customer_id = None
            request.user.save()

            messages.info(
                request, "Auto top up disabled", extra_tags="cobalt-message-success"
            )
            return redirect("payments:payments")
        else:
            return redirect("payments:payments")

    balance = get_balance(request.user)
    return render(request, "payments/cancel_autotopup.html", {"balance": balance})


###########################
# statement_admin_summary #
###########################
@login_required()
def statement_admin_summary(request):
    """Main statement page for system administrators

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    if not rbac_user_has_role(request.user, "payments.global.view"):
        return rbac_forbidden(request, "payments.global.view")

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
    stripe = StripeTransaction.objects.filter(created_date__gte=ref_date).aggregate(
        Sum("amount")
    )

    return render(
        request,
        "payments/statement_admin_summary.html",
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
        },
    )


##############
# settlement #
##############
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
                    )
                    trans_list.append(trans)

                messages.success(
                    request,
                    "Settlement processed successfully.",
                    extra_tags="cobalt-message-success",
                )
                return render(
                    request,
                    "payments/settlement-complete.html",
                    {"trans": trans_list, "total": total},
                )

    else:
        form = SettlementForm(orgs=org_list)

    return render(
        request, "payments/settlement.html", {"orgs": non_zero_orgs, "form": form}
    )


########################
# manual_adjust_member #
########################
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

        return render(request, "payments/manual_adjust_member.html", {"form": form})


########################
# manual_adjust_org    #
########################
@login_required()
def manual_adjust_org(request):
    """make a manual adjustment on an organisation account

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """
    if not rbac_user_has_role(request.user, "payments.global.edit"):
        return rbac_forbidden(request, "payments.global.edit")

    if request.method == "POST":
        form = AdjustOrgForm(request.POST)
        if form.is_valid():
            org = form.cleaned_data["organisation"]
            amount = form.cleaned_data["amount"]
            description = form.cleaned_data["description"]
            update_organisation(
                organisation=org,
                amount=amount,
                description=description,
                log_msg=description,
                source="payments",
                sub_source="manual_adjustment_org",
                payment_type="Manual Adjustment",
                member=request.user,
            )
            msg = "Manual adjustment successful. %s adjusted by %s%s" % (
                org,
                GLOBAL_CURRENCY_SYMBOL,
                amount,
            )
            messages.success(request, msg, extra_tags="cobalt-message-success")
            return redirect("payments:statement_admin_summary")

    else:
        form = AdjustOrgForm()

        return render(request, "payments/manual_adjust_org.html", {"form": form})


##########################
# stripe_webpage_confirm #
##########################
@login_required()
def stripe_webpage_confirm(request, stripe_id):
    """User has been told by Stripe that transaction went through.

    This is called by the web page after Stripe confirms the transaction is approved.
    Because this originates from the client we do not trust it, but we do move
    the status to Pending unless it is already Confirmed (timing issues).

    Args:
        request(HTTPRequest): stasndard request object
        stripe_id(int):  pk of stripe transaction

    Returns:
        Nothing.
    """

    stripe = get_object_or_404(StripeTransaction, pk=stripe_id)
    if stripe.status == "Intent":
        print("Stripe status is intend - updating")
        stripe.status = "Pending"
        stripe.save()

    return HttpResponse("ok")


############################
# stripe_autotopup_confirm #
############################
@login_required()
def stripe_autotopup_confirm(request):
    """User has been told by Stripe that auto top up went through.

    This is called by the web page after Stripe confirms that auto top up is approved.
    Because this originates from the client we do not trust it, but we do move
    the status to Pending unless it is already Confirmed (timing issues).

    For manual payments we update the transaction, but for auto top up there is
    no transaction so we record this on the User object.

    Args:
        request(HTTPRequest): stasndard request object

    Returns:
        Nothing.
    """

    if request.user.stripe_auto_confirmed == "Off":
        request.user.stripe_auto_confirmed = "Pending"
        request.user.save()

    return HttpResponse("ok")


############################
# stripe_autotopup_confirm #
############################
@login_required()
def stripe_autotopup_off(request):
    """Switch off auto top up

    This is called by the web page when a user submits new card details to
    Stripe. This is the latest point that we can turn it off in case the
    user aborts the change.

    Args:
        request(HTTPRequest): stasndard request object

    Returns:
        Nothing.
    """

    request.user.stripe_auto_confirmed = "Off"
    request.user.save()

    return HttpResponse("ok")


######################
# stripe_pending     #
######################
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
        stripe_latest = StripeTransaction.objects.filter(status="Complete").latest(
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
        "payments/stripe_pending.html",
        {
            "stripe_manual_pending": stripe_manual_pending,
            "stripe_manual_intent": stripe_manual_intent,
            "stripe_latest": stripe_latest,
            "stripe_auto_pending": stripe_auto_pending,
        },
    )


#################################
#  admin_members_with_balance   #
#################################
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
        request, "payments/admin_members_with_balance.html", {"things": things}
    )


#################################
#  admin_orgs_with_balance      #
#################################
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

    return render(request, "payments/admin_orgs_with_balance.html", {"things": things})


#####################################
#  admin_members_with_balance_csv   #
#####################################
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


#####################################
#  admin_orgs_with_balance_csv      #
#####################################
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


###################################
# admin_view_manual_adjustments   #
###################################
@login_required()
def admin_view_manual_adjustments(request):
    """Shows any open balances held by orgs - as CSV

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse (Can be CSV)
    """

    if not rbac_user_has_role(request.user, "payments.global.view"):
        return rbac_forbidden(request, "payments.global.view")

    if request.method == "POST":
        form = DateForm(request.POST)
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

            manual_member = MemberTransaction.objects.filter(
                type="Manual Adjustment"
            ).filter(created_date__range=(from_date, to_date))
            manual_org = OrganisationTransaction.objects.filter(
                type="Manual Adjustment"
            ).filter(created_date__range=(from_date, to_date))

            if "export" in request.POST:

                local_dt = timezone.localtime(timezone.now(), TZ)
                today = dateformat.format(local_dt, "Y-m-d H:i:s")

                response = HttpResponse(content_type="text/csv")
                response[
                    "Content-Disposition"
                ] = 'attachment; filename="manual-adjustments.csv"'

                writer = csv.writer(response)
                writer.writerow(
                    [
                        "Manual Adjustments",
                        "Downloaded by %s" % request.user.full_name,
                        today,
                    ]
                )

                # Members

                writer.writerow(
                    [
                        "Date",
                        "Administrator",
                        "Transaction Type",
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
                            member.member,
                            member.description,
                            member.amount,
                        ]
                    )

                # Organisations
                writer.writerow("")
                writer.writerow("")

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
                    local_dt = timezone.localtime(member.created_date, TZ)

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

            else:
                return render(
                    request,
                    "payments/admin_view_manual_adjustments.html",
                    {
                        "form": form,
                        "manual_member": manual_member,
                        "manual_org": manual_org,
                    },
                )

        else:
            print(form.errors)

    else:
        form = DateForm()

    return render(
        request, "payments/admin_view_manual_adjustments.html", {"form": form}
    )


###################################
# admin_view_stripe_transactions  #
###################################
@login_required()
def admin_view_stripe_transactions(request):
    """Shows stripe transactions for an admin

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse (can be CSV)
    """

    if not rbac_user_has_role(request.user, "payments.global.view"):
        return rbac_forbidden(request, "payments.global.view")

    if request.method == "POST":
        form = DateForm(request.POST)
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
                StripeTransaction.objects.filter(
                    created_date__range=(from_date, to_date)
                )
                .exclude(stripe_method=None)
                .order_by("-created_date")
            )

            for stripe_item in stripes:
                stripe_item.amount_settle = (float(stripe_item.amount) - 0.3) * 0.9825
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
                things = cobalt_paginator(request, stripes)
                return render(
                    request,
                    "payments/admin_view_stripe_transactions.html",
                    {"form": form, "things": things},
                )

        else:
            print(form.errors)

    else:
        form = DateForm()

    return render(
        request, "payments/admin_view_stripe_transactions.html", {"form": form}
    )


##########################################
# admin_view_stripe_transaction_details  #
##########################################
@login_required()
def admin_view_stripe_transaction_detail(request, stripe_transaction_id):
    """Shows stripe transaction details for an admin

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    if not rbac_user_has_role(request.user, "payments.global.view"):
        return rbac_forbidden(request, "payments.global.view")

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
        "payments/admin_view_stripe_transaction_detail.html",
        {"stripe_item": stripe_item},
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

    if not rbac_user_has_role(request.user, "payments.manage.%s.view" % org_id):
        if not rbac_user_has_role(request.user, "payments.global.view"):
            return rbac_forbidden(request, "payments.manage.%s.view" % org_id)

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
                log_msg=f"Transfer from {organisation} to {member}",
                source="payments",
                sub_source="member_transfer_org",
                payment_type="Member Transfer",
                member=member,
            )

            update_account(
                member=member,
                amount=amount,
                description=description,
                log_msg=f"Transfer to {member} from {organisation}",
                source="payments",
                sub_source="manual_adjust_member",
                payment_type="Manual Adjustment",
                organisation=organisation,
            )

            # Notify member
            email_body = f"<b>{organisation}</b> has transferred {GLOBAL_CURRENCY_SYMBOL}{amount:.2f} into your {BRIDGE_CREDITS} account.<br><br>The description was: {description}.<br><br>Please contact {organisation} directly if you have any queries. This transfer was made by {request.user}.<br><br>"
            context = {
                "name": member.first_name,
                "title": "Transfer from %s" % organisation,
                "email_body": email_body,
                "host": COBALT_HOSTNAME,
                "link": "/payments",
                "link_text": "View Statement",
            }

            html_msg = render_to_string("notifications/email_with_button.html", context)

            # send
            contact_member(
                member=member,
                msg="Transfer from %s - %s%s"
                % (organisation, GLOBAL_CURRENCY_SYMBOL, amount),
                contact_type="Email",
                html_msg=html_msg,
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
        "payments/member_transfer_org.html",
        {"form": form, "balance": balance, "org": organisation},
    )


@login_required()
def admin_payments_static(request):
    """Manage static data for payments

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    if not rbac_user_has_role(request.user, "payments.global.edit"):
        return rbac_forbidden(request, "payments.global.edit")

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
        "payments/admin_payments_static.html",
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
        "payments/admin_payments_static_history.html",
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
        "payments/admin_payments_static_org_override.html",
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
        "payments/admin_payments_static_org_override_add.html",
        {"form": form},
    )


@login_required()
def admin_payments_static_org_override_delete(request, item_id):
    """Manage static data for individual orgs (override default values)
    This screen deletes an override

    Args:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    if not rbac_user_has_role(request.user, "payments.global.edit"):
        return rbac_forbidden(request, "payments.global.edit")

    item = get_object_or_404(OrganisationSettlementFees, pk=item_id)

    item.delete()

    messages.success(request, "Entry deleted", extra_tags="cobalt-message-success")
    return redirect("payments:admin_payments_static_org_override")
