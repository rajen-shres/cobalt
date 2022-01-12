import csv
from datetime import timedelta

import stripe
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone, dateformat

from accounts.models import User, TeamMate
from cobalt.settings import (
    STRIPE_SECRET_KEY,
    AUTO_TOP_UP_DEFAULT_AMT,
    AUTO_TOP_UP_MAX_AMT,
    GLOBAL_CURRENCY_SYMBOL,
    BRIDGE_CREDITS,
    COBALT_HOSTNAME,
)
from logs.views import log_event
from notifications.notifications_views.core import contact_member
from payments.forms import MemberTransfer, ManualTopup
from payments.models import MemberTransaction, PaymentStatic, StripeTransaction
from payments.payments_views.admin import refund_stripe_transaction_sub
from payments.payments_views.core import (
    get_balance,
    payment_api,
    auto_topup_member,
    stripe_current_balance,
    TZ,
    statement_common,
)
from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden
from utils.utils import cobalt_paginator


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

    # Check for refund eligible items
    payment_static = PaymentStatic.objects.filter(active=True).last()
    ref_date = timezone.now() - timedelta(weeks=payment_static.stripe_refund_weeks)

    for thing in things:
        if (
            thing.stripe_transaction
            and thing.stripe_transaction.stripe_receipt_url
            and thing.stripe_transaction.status != "Refunded"
            and balance - thing.amount >= 0.0
            and thing.created_date > ref_date
        ):
            thing.show_refund = True

    return render(
        request,
        "payments/players/statement.html",
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
        "payments/players/autotopup.html",
        {"warn": warn, "topup": topup, "balance": balance},
    )


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
        "payments/players/member_transfer.html",
        {"form": form, "recents": recent_transfer_to, "balance": balance},
    )


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
                    request,
                    "payments/players/checkout.html",
                    {"trans": trans, "msg": msg},
                )
        # else:
        #     print(form.errors)

    else:
        form = ManualTopup(balance=balance)

    return render(
        request,
        "payments/players/manual_topup.html",
        {
            "form": form,
            "balance": balance,
            "remaining_balance": AUTO_TOP_UP_MAX_AMT - balance,
        },
    )


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
    return render(
        request, "payments/players/cancel_autotopup.html", {"balance": balance}
    )


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


@login_required()
def stripe_autotopup_confirm(request):
    """User has been told by Stripe that auto top up went through.

    This is called by the web page after Stripe confirms that auto top up is approved.
    Because this originates from the client we do not trust it, but we do move
    the status to Pending unless it is already Confirmed (timing issues).

    For manual payments we update the transaction, but for auto top up there is
    no transaction so we record this on the User object.

    Args:
        request(HTTPRequest): standard request object

    Returns:
        Nothing.
    """

    if request.user.stripe_auto_confirmed == "Off":
        request.user.stripe_auto_confirmed = "Pending"
        request.user.save()

    return HttpResponse("ok")


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


@login_required()
def refund_stripe_transaction(request, stripe_transaction_id):
    """Allows a user to refund a Stripe transaction

    Args:
        stripe_transaction_id:
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    stripe_item = get_object_or_404(StripeTransaction, pk=stripe_transaction_id)

    # Calculate how much refund is left in case already partly refunded
    stripe_item.refund_left = stripe_item.amount - stripe_item.refund_amount

    member_balance = get_balance(stripe_item.member)
    payment_static = PaymentStatic.objects.filter(active=True).last()
    balance_after = float(member_balance) - float(stripe_item.refund_left)
    bridge_credit_charge = float(stripe_item.refund_left)
    member_card_refund = (
        bridge_credit_charge
        * (100.0 - float(payment_static.stripe_refund_percentage_charge))
        / 100.0
    )

    # Is this allowed?

    if stripe_item.member != request.user:
        messages.error(
            request,
            "Action Prohibited - transaction is not yours",
            extra_tags="cobalt-message-error",
        )
        return redirect("payments:statement")

    if not stripe_item.stripe_receipt_url:
        messages.error(
            request,
            "Invalid transaction for a refund",
            extra_tags="cobalt-message-error",
        )
        return redirect("payments:statement")

    if stripe_item.status == "Refunded":
        messages.error(
            request, "Transaction already refunded", extra_tags="cobalt-message-error"
        )
        return redirect("payments:statement")

    if balance_after < 0.0:
        messages.error(
            request,
            "Cannot refund. Balance will be negative",
            extra_tags="cobalt-message-error",
        )
        return redirect("payments:statement")

    if stripe_current_balance() - bridge_credit_charge < 0.0:
        messages.error(
            request,
            "Cannot refund. We have insufficient funds available with Stripe. Please try again later.",
            extra_tags="cobalt-message-error",
        )
        return redirect("payments:statement")

    ref_date = timezone.now() - timedelta(weeks=payment_static.stripe_refund_weeks)
    if stripe_item.created_date <= ref_date:
        messages.error(
            request,
            "Cannot refund. Transaction is too old.",
            extra_tags="cobalt-message-error",
        )
        return redirect("payments:statement")

    if request.method == "POST":

        stripe_amount = int(member_card_refund * 100)

        stripe.api_key = STRIPE_SECRET_KEY

        try:
            rc = stripe.Refund.create(
                charge=stripe_item.stripe_reference,
                amount=stripe_amount,
            )

        except stripe.error.InvalidRequestError as e:
            log_event(
                user=request.user.full_name,
                severity="HIGH",
                source="Payments",
                sub_source="User initiated refund",
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
                message=f"User Refund. Unknown status from stripe refund. Stripe Item:{stripe_item}    Return Code{rc}",
            )

            return render(
                request,
                "payments/admin/payments_refund_error.html",
                {"rc": rc, "stripe_item": stripe_item},
            )

        # Call atomic database update
        refund_stripe_transaction_sub(
            stripe_item, stripe_item.refund_left, "Card refund"
        )

        # Notify member
        email_body = f"""You have requested to refund a card transaction. You will receive a refund of
        {GLOBAL_CURRENCY_SYMBOL}{member_card_refund:.2f} to your card.<br><br>
         Please note that It can take up to two weeks for the money to appear in your card statement.<br><br>
         Your {BRIDGE_CREDITS} account balance has been reduced to reflect this refund. You can check your new balance
         using the link below.<br><br>
         """

        # send
        contact_member(
            member=stripe_item.member,
            msg="Card Refund - %s%s" % (GLOBAL_CURRENCY_SYMBOL, member_card_refund),
            contact_type="Email",
            html_msg=email_body,
            link="/payments",
            subject="Card Refund",
            link_text="View Statement",
        )

        messages.success(
            request, "Refund Request Submitted", extra_tags="cobalt-message-success"
        )
        return redirect("payments:statement")

    return render(
        request,
        "payments/players/refund_stripe_transaction.html",
        {
            "stripe_item": stripe_item,
            "payment_static": payment_static,
            "member_balance": member_balance,
            "balance_after": balance_after,
            "bridge_credit_charge": bridge_credit_charge,
            "member_card_refund": member_card_refund,
        },
    )
