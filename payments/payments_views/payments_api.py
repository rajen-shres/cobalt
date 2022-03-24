import logging

from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse

from cobalt.settings import (
    AUTO_TOP_UP_LOW_LIMIT,
    BRIDGE_CREDITS,
    GLOBAL_CURRENCY_SYMBOL,
)
from logs.views import log_event
from notifications.notifications_views.core import send_cobalt_email_with_template
import payments.payments_views.core as payments_core
from payments.models import StripeTransaction

logger = logging.getLogger("cobalt")


def payment_api_interactive(
    request,
    member,
    description,
    amount,
    organisation=None,
    other_member=None,
    payment_type="Miscellaneous",
    next_url=None,
    route_code=None,
    route_payload=None,
    book_internals=True,
):
    """Payments API when we have an attached user. This will try to make a payment and if need be
        take the user to the Stripe payment screen to handle a manual payment.

        For auto top up users, or users with enough money, this is a synchronous process and
        we will return the next_url to the user.

        For manual payments, the Stripe process is asynchronous. We hand the user off to Stripe
        and only know if their payment worked when Stripe calls us back through the webhook. We use
        a route_code to know what function to call when the webhook is triggered and the route_payload
        is passed so the calling module knows what this refers to.

        args:
            request - Standard request object
            description - text description of the payment
            amount - A positive amount is a charge, a negative amount is an incoming payment.
            member - User object related to the payment
            organisation - linked organisation
            other_member - User object
            payment_type - description of payment
            next_url - where to take the user next
            route_code - used by the callback to know which function to call upon the payment going through
            route_payload - identifier to pass when making the callback
            book_internals - sometimes the calling module wants to book the internal deals (not Stripe) themselves
                             for example, event entry may be booking a whole team of entries as part of this so we
                             only want the stripe transaction to go through and the call back will book all of the
                             individual deals. Default is to have us book the internals too.

    returns:
        HttpResponse - either the Stripe manual payment screen or the next_url

    """

    if not next_url:  # where to next
        next_url = reverse("dashboard:dashboard")

    # First try to make the payment without the user's involvement
    if payment_api_batch(
        member=member,
        description=description,
        amount=amount,
        organisation=organisation,
        other_member=other_member,
        payment_type=payment_type,
        book_internals=book_internals,
    ):
        logger.info(f"{request.user} paid {amount:.2f} for {description}")

        # Call the callback
        payments_core.callback_router(
            route_code=route_code, route_payload=route_payload
        )

        # Return
        msg = _success_msg_for_user(amount, other_member, organisation)
        messages.success(request, msg, extra_tags="cobalt-message-success")
        return redirect(next_url)

    # Didn't work automatically, we need to get the user to pay manually
    balance = float(payments_core.get_balance(member))
    amount = float(amount)

    # Create Stripe Transaction
    trans = StripeTransaction()
    trans.description = description
    trans.amount = amount - balance
    trans.member = member
    trans.route_code = route_code
    trans.route_payload = route_payload
    trans.linked_amount = amount
    trans.linked_member = other_member
    trans.linked_organisation = organisation
    trans.linked_transaction_type = payment_type
    trans.save()

    msg = _manual_payment_description(balance, amount, other_member, description)

    next_url_name = _next_url_name_from_url(next_url)

    logger.info(
        f"{request.user} handed to Stripe manual screen to pay {amount:.2f} for {description}"
    )

    return render(
        request,
        "payments/players/checkout.html",
        {
            "trans": trans,
            "msg": msg,
            "next_url": next_url,
            "next_url_name": next_url_name,
        },
    )


def _manual_payment_description(balance, amount, other_member, description):
    """Format the message correctly"""
    if other_member:  # transfer to another member
        if balance > 0.0:
            return f"""Partial payment for transfer to {other_member} ({description}).
                      <br>
                      Also using your current balance
                      of {GLOBAL_CURRENCY_SYMBOL}{balance:.2f} to make a total payment of
                      {GLOBAL_CURRENCY_SYMBOL}{amount:.2f}.
                 """

        return f"Payment to {other_member} ({description})"

    if balance > 0.0:  # Use existing balance
        return f"""Partial payment for {description}.
                  <br>
                  Also using your current balance
                  of {GLOBAL_CURRENCY_SYMBOL}{balance:.2f} to make a total payment of
                  {GLOBAL_CURRENCY_SYMBOL}{amount:.2f}.
             """

    return f"Payment for: {description}"


def _next_url_name_from_url(next_url):
    """Try to work out what to describe the next_url as"""
    # TODO: Move this to the calling function to provide as a parameter

    if next_url.find("events") >= 0:
        return "Events"
    elif next_url.find("dashboard") >= 0:
        return "Dashboard"
    elif next_url.find("payments") >= 0:
        return "your statement"
    return "Next"


def _success_msg_for_user(amount, other_member, organisation):
    """Build message to show on user's next screen"""
    if other_member:
        return f"Payment of {amount:.2f} to {other_member} successful"
    if organisation:
        return f"Payment of {amount:.2f} to {organisation} successful"
    # Shouldn't get here
    return f"Payment of {amount:.2f} successful"


def payment_api_batch(
    member,
    description,
    amount,
    organisation=None,
    other_member=None,
    payment_type=None,
    book_internals=True,
):
    """This API is used by other parts of the system to make payments or
    fail. It will use existing funds or try to initiate an auto top up.
    Use payment_api_interactive() if you wish the user to be taken to the manual
    payment screen.

    We accept either organisation as the counterpart for this payment or
    other_member. If the calling function wishes to book their own transactions
    they can pass us neither parameter.

    For Events the booking of the internal transactions is done in the callback
    so that we can have individual transactions that are easier to map. The
    optional parameter book_internals handles this. If this is set to false
    then only the necessary Stripe transactions are executed by payment_api.

    args:
        description - text description of the payment
        amount - A positive amount is a charge, a negative amount is an incoming payment.
        member - User object related to the payment
        organisation - linked organisation
        other_member - User object
        payment_type - description of payment
        book_internals - sometimes the calling module wants to book the internal deals (not Stripe) themselves
                         for example, event entry may be booking a whole team of entries as part of this so we
                         only want the stripe transaction to go through and the call back will book all of the
                         individual deals. Default is to have us book the internals too.

    returns:
        bool - success or failure
    """

    if other_member and organisation:  # one or the other, not both
        log_event(
            user="Stripe API",
            severity="CRITICAL",
            source="Payments",
            sub_source="payments_api",
            message="Received both other_member and organisation. Code Error.",
        )
        return False

    balance = float(payments_core.get_balance(member))
    amount = float(amount)

    if not payment_type:
        payment_type = "Miscellaneous"

    if amount <= balance:
        return _payment_with_sufficient_funds(
            member,
            amount,
            description,
            organisation,
            other_member,
            payment_type,
            balance,
            book_internals,
        )
    else:
        return _payment_with_insufficient_funds(
            member,
            amount,
            description,
            organisation,
            other_member,
            payment_type,
            balance,
            book_internals,
        )


def _payment_with_sufficient_funds(
    member,
    amount,
    description,
    organisation,
    other_member,
    payment_type,
    balance,
    book_internals,
):
    """Handle a payment when the user has enough money to cover it"""

    # Record the internal transactions unless asked not to by calling module
    if book_internals:
        _update_account_entries_for_member_payment(
            member, amount, description, organisation, other_member, payment_type
        )

    # For member to member transfers, we notify both parties
    if other_member:
        notify_member_to_member_transfer(member, other_member, amount, description)

    # check for auto top up required - if user not set for auto topup then ignore
    _check_for_auto_topup(member, amount, balance)

    return True


def _update_account_entries_for_member_payment(
    member, amount, description, organisation, other_member, payment_type
):
    """Make the actual updates to the tables for a member transaction. Doesn't check anything, just does the work."""

    payments_core.update_account(
        member=member,
        amount=-amount,
        organisation=organisation,
        other_member=other_member,
        description=description,
        payment_type=payment_type,
        log_msg=None,
        source=None,
        sub_source=None,
    )

    # If we got an organisation then make their payment too
    if organisation:
        payments_core.update_organisation(
            organisation=organisation,
            amount=amount,
            description=description,
            payment_type=payment_type,
            member=member,
            log_msg=None,
            source=None,
            sub_source=None,
        )

    # If we got an other_member then make their payment too
    if other_member:
        payments_core.update_account(
            amount=amount,
            description=description,
            payment_type=payment_type,
            other_member=member,
            member=other_member,
            log_msg=None,
            source=None,
            sub_source=None,
        )


def notify_member_to_member_transfer(member, other_member, amount, description):
    """For member to member transfers we email both members to confirm"""

    logger.info(f"{member} transfer to {other_member} {amount}")

    # Member email
    email_body = f"""You have transferred {amount:.2f} credits into the {BRIDGE_CREDITS} account
                    of {other_member}.
                    <br><br>
                    The description was: {description}.
                    <br><br>Please contact us immediately if you do not recognise this transaction.
                    <br><br>"""

    context = {
        "name": member.first_name,
        "title": f"Transfer to {other_member.full_name}",
        "email_body": email_body,
        "link": "/payments",
        "link_text": "View Statement",
        "box_colour": "primary",
    }

    send_cobalt_email_with_template(
        to_address=member.email, context=context, priority="now"
    )

    # Other Member email
    email_body = f"""<b>{member}</b> has transferred {amount:.2f} credits into your {BRIDGE_CREDITS} account.
                    <br><br>
                    The description was: {description}.
                    <br><br>
                    Please contact {member.first_name} directly if you have any queries.<br><br>
                    """

    context = {
        "name": other_member.first_name,
        "title": f"Transfer from {member.full_name}",
        "email_body": email_body,
        "link": "/payments",
        "link_text": "View Statement",
        "box_colour": "primary",
    }

    send_cobalt_email_with_template(
        to_address=other_member.email, context=context, priority="now"
    )


def _check_for_auto_topup(member, amount, balance):
    """Check if member needs to be filled up after this transaction.
    We don't worry about whether this works or not. If it fails then the auto_topup_member function
    will take care of it.
    """

    if (
        member.stripe_auto_confirmed == "On"
        and balance - amount < AUTO_TOP_UP_LOW_LIMIT
    ):
        payments_core.auto_topup_member(member)


def _payment_with_insufficient_funds(
    member,
    amount,
    description,
    organisation,
    other_member,
    payment_type,
    balance,
    book_internals,
):
    """Handle a member not having enough money to pay"""

    # We can't do anything if auto top up is off
    if member.stripe_auto_confirmed != "On":
        return False

    topup_required = calculate_auto_topup_amount(member, amount, balance)
    return_code, _ = payments_core.auto_topup_member(
        member, topup_required=topup_required
    )

    if return_code:
        # We should now have sufficient funds but lets check just to be sure
        balance = float(payments_core.get_balance(member))

        if amount <= balance and book_internals:
            _update_account_entries_for_member_payment(
                member, amount, description, organisation, other_member, payment_type
            )
            # For member to member transfers, we notify both parties
            if other_member:
                notify_member_to_member_transfer(
                    member, other_member, amount, description
                )

        return True

    return False


def calculate_auto_topup_amount(member, amount, balance):
    """calculate required top up amount
    Generally top by the largest of amount and auto_amount, BUT if the
    balance after that will be low enough to require another top up then
    we top up by increments of the top up amount.
    """
    topup_required = amount  # normal top up

    if balance < AUTO_TOP_UP_LOW_LIMIT:

        topup_required = member.auto_amount if member.auto_amount >= amount else amount

        # check if we will still be under threshold
        if balance + topup_required - amount < AUTO_TOP_UP_LOW_LIMIT:
            min_required_amt = amount - balance + AUTO_TOP_UP_LOW_LIMIT
            n = int(min_required_amt / member.auto_amount) + 1
            topup_required = member.auto_amount * n

    elif member.auto_amount >= amount:  # use biggest
        topup_required = member.auto_amount

    return topup_required
