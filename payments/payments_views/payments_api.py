import logging

from django.template.loader import render_to_string

from cobalt.settings import AUTO_TOP_UP_LOW_LIMIT, BRIDGE_CREDITS
from logs.views import log_event
from notifications.notifications_views.core import send_cobalt_email_with_template
import payments.payments_views.core as payments_core

logger = logging.getLogger("cobalt")


def payment_api_batch(
    member,
    description,
    amount,
    organisation=None,
    other_member=None,
    payment_type=None,
):
    """This API is used by other parts of the system to make payments or
    fail. It will use existing funds or try to initiate an auto top up.
    Use another API call if you wish the user to be taken to the manual
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
        )


def _payment_with_sufficient_funds(
    member, amount, description, organisation, other_member, payment_type, balance
):
    """Handle a payment when the user has enough money to cover it"""

    _update_account_entries_for_member_payment(
        member, amount, description, organisation, other_member, payment_type
    )

    # For member to member transfers, we notify both parties
    if other_member:
        _notify_member_to_member_transfer(member, amount, description, organisation)

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


def _notify_member_to_member_transfer(member, amount, description, other_member):
    """For member to member transfers we email both members to confirm"""

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
        "box_colour": "rose",
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
        "box_colour": "rose",
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
    member, amount, description, organisation, other_member, payment_type, balance
):
    """Handle a member not having enough money to pay"""

    # We can't do anything if auto top up is off
    if member.stripe_auto_confirmed != "On":
        return False

    topup_required = _calculate_auto_topup_amount(member, amount, balance)
    return_code, _ = payments_core.auto_topup_member(
        member, topup_required=topup_required
    )

    if return_code:
        # We should now have sufficient funds but lets check just to be sure
        balance = float(payments_core.get_balance(member))

        if amount <= balance:
            _update_account_entries_for_member_payment(
                member, amount, description, organisation, other_member, payment_type
            )
            _notify_member_to_member_transfer(member, amount, description, organisation)
            return True

    return False


def _calculate_auto_topup_amount(member, amount, balance):
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
