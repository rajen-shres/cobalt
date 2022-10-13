# -*- coding: utf-8 -*-
"""Handles all activities associated with payments that do not talk to users.

This module handles all of the functions that do not interact directly with
a user. i.e. they do not generally accept a ``Request`` and return an
``HttpResponse``. Arguably these could have been put directly into models.py
but it seems cleaner to store them here.

See also `Payments Views`_. This handles the user side of the interactions.
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

.. _Payments Views:
   #module-payments.views

.. _Payments Overview:
   ./payments_overview.html

"""
import json
import logging
from json import JSONDecodeError

import pytz
import requests
import stripe
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.models import User
from cobalt.settings import (
    STRIPE_SECRET_KEY,
    STRIPE_PUBLISHABLE_KEY,
    AUTO_TOP_UP_LOW_LIMIT,
    BRIDGE_CREDITS,
    GLOBAL_CURRENCY_SYMBOL,
    TIME_ZONE,
    GLOBAL_MPSERVER,
)
import events.views.core as events_core
from logs.views import log_event
from notifications.views.core import contact_member
from payments.models import (
    StripeTransaction,
    MemberTransaction,
    OrganisationTransaction,
    StripeLog,
    UserPendingPayment,
)
from payments.views.payments_api import notify_member_to_member_transfer

TZ = pytz.timezone(TIME_ZONE)

logger = logging.getLogger("cobalt")


#######################
# get_balance_detail  #
#######################
def get_balance_detail(member):
    """Called by dashboard to show basic information

    Args:
        member: A User object - the member whose balance is required

    Returns:
        dict: Keys - balance and last_top_up

    """

    last_tran = MemberTransaction.objects.filter(member=member).last()
    if last_tran:
        return {
            "balance": last_tran.balance,
            "balance_num": last_tran.balance,
            "last_top_up": last_tran.created_date,
        }
    else:
        return {"balance": "0", "balance_num": None, "last_top_up": None}


################
# get_balance  #
################
def get_balance(member):
    """Gets member account balance

    This function returns the current balance of the member's account.

    Args:
        member (User): A User object

    Returns:
        float: The member's current balance

    """

    last_tran = MemberTransaction.objects.filter(member=member).last()
    return float(last_tran.balance) if last_tran else 0.0


###############################################
# get_balance and recent transactions for org #
###############################################
def get_balance_and_recent_trans_org(org):
    """Gets organisation account balance and most recent transactions

    This function returns the current balance of the organisation's account and the most recent transactions.

    Args:
        org (organisations.models.Organisation): An Organisation object

    Returns:
        float: The member's current balance
        list: the most recent transactions

    """

    trans = OrganisationTransaction.objects.filter(organisation=org).order_by("-pk")[
        :20
    ]

    last_tran = trans.first()

    balance = float(last_tran.balance) if last_tran else 0.0
    return balance, trans


#############################
# get_user_pending_payments #
#############################
def get_user_pending_payments(system_number):
    """Get any IOUs for this user. Called by the dashboard"""

    return UserPendingPayment.objects.filter(system_number=system_number)


################################
# stripe_manual_payment_intent #
################################
@login_required()
def stripe_manual_payment_intent(request):
    """Called from the checkout webpage.

    When a user is going to pay with a credit card we
    tell Stripe and Stripe gets ready for it. By this point in the process
    we have handed over control to the Stripe code which calls this function
    over Ajax.

    This functions expects a json payload as part of `request`.

    Args:
        request - This needs to contain a Json payload.

    Notes:
        The Json should include:
        data{"id": This is the StripeTransaction in our table that we are handling
        "amount": The amount in the system currency}

    Returns:
        json: {'publishableKey':? 'clientSecret':?}

    Notes:
        publishableKey = our Public Stripe key,
        clientSecret = client secret from Stripe

    """

    if request.method != "POST":
        return JsonResponse({"error": "POST required"})
    data = json.loads(request.body)

    # check data - do not trust it
    try:
        payload_cents = int(float(data["amount"]) * 100.0)
        payload_cobalt_pay_id = data["id"]
    except KeyError:
        log_event(
            request=request,
            user=request.user,
            severity="ERROR",
            source="Payments",
            sub_source="stripe_manual_payment_intent",
            message="Invalid payload: %s" % data,
        )
        return JsonResponse({"error": "Invalid payload"})

    # load our StripeTransaction
    try:
        our_trans = StripeTransaction.objects.get(pk=payload_cobalt_pay_id)
    except ObjectDoesNotExist:
        log_event(
            request=request,
            user=request.user,
            severity="ERROR",
            source="Payments",
            sub_source="stripe_manual_payment_intent",
            message="StripeTransaction id: %s not found" % payload_cobalt_pay_id,
        )

        return JsonResponse({"error": "Invalid payload"})

    # Check it
    if float(our_trans.amount) * 100.0 != payload_cents:
        log_event(
            request=request,
            user=request.user,
            severity="ERROR",
            source="Payments",
            sub_source="stripe_manual_payment_intent",
            message="StripeTransaction id: %s. Browser sent %s cents."
            % (payload_cobalt_pay_id, payload_cents),
        )
        return JsonResponse({"error": "Invalid payload"})

    stripe.api_key = STRIPE_SECRET_KEY

    # Create a customer so we get the email and name on the Stripe side
    # We create a new Stripe customer each time
    stripe_customer = stripe.Customer.create(
        name=request.user,
        email=request.user.email,
    )

    intent = stripe.PaymentIntent.create(
        amount=payload_cents,
        currency="aud",
        customer=stripe_customer,
        description=f"Manual Payment by {request.user}",
        metadata={
            "cobalt_pay_id": payload_cobalt_pay_id,
            "cobalt_tran_type": "Manual",
        },
    )
    log_event(
        request=request,
        user=request.user,
        severity="INFO",
        source="Payments",
        sub_source="stripe_manual_payment_intent",
        message="Created payment intent with Stripe. \
                  Cobalt_pay_id: %s"
        % payload_cobalt_pay_id,
    )

    print("Stripe manual intent successful")
    print(intent)

    # Update Status
    our_trans.status = "Intent"
    our_trans.save()

    return JsonResponse(
        {
            "publishableKey": STRIPE_PUBLISHABLE_KEY,
            "clientSecret": intent.client_secret,
        }
    )


####################################
# stripe_auto_payment_intent       #
####################################
@login_required()
def stripe_auto_payment_intent(request):
    """Called from the auto top up webpage.

    This is very similar to the one off payment. It lets Stripe
    know to expect a credit card and provides a token to confirm
    which one it is.

    When a user is going to set up a credit card we
    tell Stripe and Stripe gets ready for it. By this point in the process
    we have handed over control to the Stripe code which calls this function
    over Ajax.

    This functions expects a json payload as part of `request`.

    Args:
        request - This needs to contain a Json payload.

    Notes:
        The Json should include:
        data{"stripe_customer_id": This is the Stripe customer_id in our table
        for the customer that we are handling}

    Returns:
        json: {'publishableKey':? 'clientSecret':?}

    Notes:
        publishableKey = our Public Stripe key,
        clientSecret = client secret from Stripe

    """

    if request.method == "POST":
        stripe.api_key = STRIPE_SECRET_KEY
        intent = stripe.SetupIntent.create(
            customer=request.user.stripe_customer_id,
            description=f"Intent to set up auto pay by {request.user}",
            metadata={"cobalt_member_id": request.user.id, "cobalt_tran_type": "Auto"},
        )

        log_event(
            request=request,
            user=request.user,
            severity="INFO",
            source="Payments",
            sub_source="stripe_auto_payment_intent",
            message="Intent created for: %s" % request.user,
        )

        print("Stripe auto intent successful")
        print(intent)

        return JsonResponse(
            {
                "publishableKey": STRIPE_PUBLISHABLE_KEY,
                "clientSecret": intent.client_secret,
            }
        )

    return JsonResponse({"error": "POST required"})


###########################
# stripe_current_balance  #
###########################
def stripe_current_balance():
    """Get our (ABF) current balance with Stripe"""

    stripe.api_key = STRIPE_SECRET_KEY
    ret = stripe.Balance.retrieve()

    # Will be in cents so convert to dollars
    # TODO: make this international
    return float(ret.available[0].amount / 100.0)


#########################
# stripe_webhook_manual #
#########################
def stripe_webhook_manual(event):
    """Handles manual payment events from Stripe webhook

    Called by stripe_webhook to look after incoming manual payments.

    Args:
        event - the event payload from Stripe

    Returns:
        HTTPResponse code - 200 for success, 400 for error
    """

    # get data from payload
    charge = event.data.object

    message = f"Received charge.succeeded for Manual payment. Our id={charge.metadata.cobalt_pay_id}. Their id={charge.id}"

    # TODO: catch error if ids not present
    log_event(
        user="Stripe API",
        severity="INFO",
        source="Payments",
        sub_source="stripe_webhook",
        message=message,
    )

    logger.info(message)

    # Update StripeTransaction
    try:
        tran = StripeTransaction.objects.get(pk=charge.metadata.cobalt_pay_id)

        tran.stripe_reference = charge.id
        tran.stripe_method = charge.payment_method
        tran.stripe_currency = charge.currency
        tran.stripe_receipt_url = charge.receipt_url
        tran.stripe_brand = charge.payment_method_details.card.brand
        tran.stripe_country = charge.payment_method_details.card.country
        tran.stripe_exp_month = charge.payment_method_details.card.exp_month
        tran.stripe_exp_year = charge.payment_method_details.card.exp_year
        tran.stripe_last4 = charge.payment_method_details.card.last4
        tran.stripe_balance_transaction = event.data.object.balance_transaction
        tran.last_change_date = timezone.now()
        tran.status = "Succeeded"

        already = StripeTransaction.objects.filter(
            stripe_method=charge.payment_method
        ).exists()

        if not already:
            tran.save()
        else:
            log_event(
                user="Stripe API",
                severity="CRITICAL",
                source="Payments",
                sub_source="stripe_webhook",
                message=f"Duplicate transaction from Stripe. {charge.payment_method} already present",
            )
            return HttpResponse(status=200)

    except ObjectDoesNotExist:
        log_event(
            user="Stripe API",
            severity="CRITICAL",
            source="Payments",
            sub_source="stripe_webhook",
            message="Unable to load stripe transaction. Check StripeTransaction \
                  table. Our id=%s - Stripe id=%s"
            % (charge.metadata.cobalt_pay_id, charge.id),
        )
        # TODO: change to 400
        return HttpResponse(status=200)

    # Set the payment type - this could be for a linked transaction or a manual
    # payment.

    pay_type = "CC Payment" if tran.linked_transaction_type else "Manual Top Up"
    update_account(
        member=tran.member,
        amount=tran.amount,
        stripe_transaction=tran,
        description="Payment from card **** **** ***** %s Exp %s/%s"
        % (tran.stripe_last4, tran.stripe_exp_month, abs(tran.stripe_exp_year) % 100),
        payment_type=pay_type,
    )

    # Money in from stripe so we can now process the original transaction, if
    # we have one. For manual top ups we don't have another transaction and
    # linked_transaction_type will be None

    if tran.linked_transaction_type:

        # We could be linked to a member payment or an organisation payment
        if tran.linked_organisation:
            update_account(
                member=tran.member,
                amount=-tran.linked_amount,
                description=tran.description,
                payment_type=tran.linked_transaction_type,
                organisation=tran.linked_organisation,
            )

            # make organisation payment too
            update_organisation(
                organisation=tran.linked_organisation,
                amount=tran.linked_amount,
                description=tran.description,
                payment_type=tran.linked_transaction_type,
                member=tran.member,
            )

        if tran.linked_member:
            update_account(
                member=tran.member,
                amount=-tran.linked_amount,
                description=tran.description,
                payment_type=tran.linked_transaction_type,
                other_member=tran.linked_member,
            )

            # make member payment too
            update_account(
                member=tran.linked_member,
                other_member=tran.member,
                amount=tran.linked_amount,
                description=tran.description,
                payment_type=tran.linked_transaction_type,
            )

    # make Callback
    callback_router(tran.route_code, tran.route_payload, tran)

    # success
    return HttpResponse(status=200)


##############################
# stripe_webhook_autosetup   #
##############################
def stripe_webhook_autosetup(event):
    """Handles auto top up setup events from Stripe webhook

    Called by stripe_webhook to look after successful incoming auto top up set ups.

    Args:
        event - the event payload from Stripe

    Returns:
        HTTPResponse code - 200 for success, 400 for error
    """

    # Get customer id
    try:
        stripe_customer = event.data.object.customer
    except AttributeError:
        log_event(
            user="Stripe API",
            severity="CRITICAL",
            source="Payments",
            sub_source="stripe_webhook",
            message="Error retrieving Stripe customer id from message",
        )
        logger.critical("No customer found on stripe API call")

        # If we reply with 400 for example, Stripe will continue to resend. It won't help.
        return HttpResponse(status=200)

    # find member
    member = User.objects.filter(stripe_customer_id=stripe_customer).last()
    if not member:
        log_event(
            user="Stripe API",
            severity="CRITICAL",
            source="Payments",
            sub_source="stripe_webhook",
            message=f"Error cannot find member with stripe_customer_id={stripe_customer}",
        )
        logger.critical(f"Member not found for stripe customer: {stripe_customer}")
        return HttpResponse(status=400)

    logger.info(f"{member} got auto top up response from Stripe")

    # confirm card set up
    member.stripe_auto_confirmed = "On"
    member.save()

    # check if we should make an auto top up now
    balance = get_balance(member)

    if balance < AUTO_TOP_UP_LOW_LIMIT:
        (return_code, message) = auto_topup_member(member)
        if return_code:  # success
            log_event(
                user="Stripe API",
                severity="INFO",
                source="Payments",
                sub_source="stripe_webhook",
                message=message,
            )
        else:  # failure
            log_event(
                user="Stripe API",
                severity="ERROR",
                source="Payments",
                sub_source="stripe_webhook",
                message=message,
            )
        return HttpResponse(status=200)
    return HttpResponse(status=200)


####################
# stripe_webhook   #
####################
@require_POST
@csrf_exempt
def stripe_webhook(request):
    """Callback from Stripe webhook

    In development, Stripe sends us everything. In production we can configure
    the events that we receive. This is the only way for Stripe to communicate
    with us.

    Note:
        Stripe sends us multiple similar things, for example *payment.intent.succeeded*
        will accompany anything that uses a payment intent. Be careful to only
        handle one out of the multiple events.

    For **manual payments** we can receive:

    * payment.intent.created - ignore
    * charge.succeeded - process
    * payment.intent.succeeded - ignore

    For **automatic payment set up**, we get:

    * customer.created - ignore
    * setup_intent.created - ignore
    * payment_method.attached - process
    * setup_intent.succeeded - ignore

    For **automatic payments** we get:

    * payment_intent.succeeded - ignore
    * payment_intent.created - ignore
    * charge_succeeded - ignore (we already know this from the API call)

    **Meta data**

    We use meta data to track what the event related to. This is added by us
    when we call Stripe and returned to us by Stripe in the callback.

    Fields used:

    * **cobalt_tran_type** - either *Manual* or *Auto* for manual and auto top up
      transactions. If this is missing then the transaction is invalid.
    * **cobalt_pay_id** - for manual payments this is the linked transaction in
      MemberTransaction.

    Args:
        Stripe json payload - see Stripe documentation

    Returns:
        HTTPStatus Code
    """
    payload = request.body
    event = None

    try:
        event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)
    except ValueError as error:
        # Invalid payload
        log_event(
            user="Stripe API",
            severity="HIGH",
            source="Payments",
            sub_source="stripe_webhook",
            message=f"Invalid Payload in message from Stripe: {error}",
        )
        logger.critical(f"Invalid Payload in message from Stripe: {error}")

        return HttpResponse(status=400)

    # Log message
    stripe_log = StripeLog(event=event)
    stripe_log.save()

    # We get some noise in test environments so filter that out
    if event.type not in ["charge.succeeded", "payment_method.attached"]:
        logger.info(
            f"Ignoring event type from Stripe that we do not want: {event.type}"
        )
        return HttpResponse()

    try:
        tran_type = event.data.object.metadata.cobalt_tran_type
    except AttributeError:
        log_event(
            user="Stripe API",
            severity="CRITICAL",
            source="Payments",
            sub_source="stripe_webhook",
            message="cobalt_tran_type missing from Stripe webhook",
        )
        logger.critical(
            f"cobalt_tran_type missing from Stripe webhook. metadata was {event.data}"
        )
        # TODO: change to 400
        return HttpResponse(status=200)

    stripe_log.cobalt_tran_type = tran_type
    stripe_log.event_type = event.type
    stripe_log.save()

    # We only process change succeeded for Manual charges - for auto topup
    # we get this synchronously through the API call, this is additional info.
    # Don't process it twice.

    if event.type == "charge.succeeded" and tran_type == "Manual":
        return stripe_webhook_manual(event)

    elif event.type == "payment_method.attached":  # auto top up set up successful
        return stripe_webhook_autosetup(event)

    else:
        # Unexpected event type
        log_event(
            user="Stripe API",
            severity="HIGH",
            source="Payments",
            sub_source="stripe_webhook",
            message="Unexpected event received from Stripe - " + event.type,
        )

        print("Unexpected event found - " + event.type)
        # TODO - change to 400
        return HttpResponse(status=200)


#########################
# callback_router       #
#########################
def callback_router(
    route_code, route_payload, stripe_transaction=None, status="Success"
):
    """Central function to handle callbacks

    Callbacks are an asynchronous way for us to let the calling application
    know if a payment succeeded or not.

    We could use a routing table for this but there will only ever be a small
    number of callbacks in Cobalt so we are okay to hardcode it.

    Args:
        route_code: (str) hard coded value to map to a function call
        route_payload (str) value to return to function
        stripe_transaction: StripeTransaction. Optional. Sometimes (e.g. member transfer) we want to get the data from
                            the Stripe transaction rather than the payload.
        status: Success (default) or Failure. Did the payment work or not.

    Returns:
        Nothing
    """

    if not route_code:  # do nothing if no route_code passed
        return

    # Payments made by the main entrant to an event
    if route_code == "EVT":
        events_core.events_payments_primary_callback(status, route_payload)

    # Payments made by other entrants to an event
    elif route_code == "EV2":
        events_core.events_payments_secondary_callback(status, route_payload)

    # Member to member transfers - we also pass the Stripe transaction
    elif route_code == "M2M":
        member_to_member_transfer_callback(stripe_transaction)

    # User Pending Payment
    elif route_code == "UPP":
        from payments.views.players import user_pending_payment_callback

        user_pending_payment_callback(status, route_payload)

    else:
        log_event(
            user="Stripe API",
            severity="CRITICAL",
            source="Payments",
            sub_source="stripe_webhook",
            message="Unable to make callback. Invalid route_code: %s" % route_code,
        )


######################
# update_account     #
######################
def update_account(
    member,
    amount,
    description,
    payment_type,
    stripe_transaction=None,
    other_member=None,
    organisation=None,
    session=None,
):
    """Function to update a customer account by adding a transaction.

    args:
        member (User): owner of the account
        amount (float): value (plus is a deduction, minus is a credit)
        description (str): to appear on statement
        payment_type (str): type of payment
        stripe_transaction (StripeTransaction, optional): linked Stripe transaction
        other_member (User, optional): linked member
        organisation (organisations.models.Organisation, optional): linked organisation
        session (club_sessions.models.Session, optional): club_session.session linked to this transaction

    returns:
        MemberTransaction

    """
    # Get new balance
    balance = get_balance(member) + float(amount)

    # Create new MemberTransaction entry
    act = MemberTransaction()
    act.member = member
    act.amount = amount
    act.stripe_transaction = stripe_transaction
    act.other_member = other_member
    act.organisation = organisation
    act.balance = balance
    act.description = description
    act.type = payment_type
    if session:
        act.club_session_id = session.id

    act.save()

    return act


#########################
# update_organisation   #
#########################
def update_organisation(
    organisation,
    amount,
    description,
    payment_type,
    other_organisation=None,
    member=None,
    bank_settlement_amount=None,
    session=None,
):
    """method to update an organisations account

    args:
        organisation (organisations.models.Organisation): organisation to update
        amount (float): value (plus is a deduction, minus is a credit)
        description (str): to appear on statement
        payment_type (str): type of payment
        member (User, optional): linked member
        other_organisation (organisations.model.Organisation, optional): linked organisation
        bank_settlement_amount (float): How much we expect to be settled. Used for ABF deducting fees for card payments
        session (club_sessions.models.Session, optional): club_session.session linked to this transaction
    """

    last_tran = OrganisationTransaction.objects.filter(organisation=organisation).last()
    balance = last_tran.balance if last_tran else 0.0
    act = OrganisationTransaction()
    act.organisation = organisation
    act.member = member
    act.amount = amount
    act.other_organisation = other_organisation
    act.balance = float(balance) + float(amount)
    act.description = description
    act.type = payment_type
    act.bank_settlement_amount = bank_settlement_amount
    if session:
        act.club_session_id = session.id

    act.save()

    return act


###########################
# auto_topup_member       #
###########################
def auto_topup_member(member, topup_required=None, payment_type="Auto Top Up"):
    """process an auto top up for a member.

    Internal function to handle a member needing to process an auto top up.
    This function deals with successful top ups and failed top ups. For
    failed top ups it will notify the user and disable auto topups. It is
    the calling functions problem to handle the consequences of the non-payment.

    Args:
        member - a User object.
        topup_required - the amount of the top up (optional). This is required if the payment
                            is larger than the top up amount. e.g. balance is 25, top up amount
                            is 50, payment is 300.
        payment_type - defaults to Auto Top Up. We allow this to be overridden so that a member
                            manually topping up their account using their registered auto top
                            up card get the payment type of Manual Top Up on their statement.

    Returns:
        return_code - True for success, False for failure
        message - explanation

    """

    stripe.api_key = STRIPE_SECRET_KEY

    if member.stripe_auto_confirmed != "On":
        logger.warning(f"{member} not set up for auto top up")
        return False, "Member not set up for Auto Top Up"

    if not member.stripe_customer_id:
        logger.warning(f"{member} no stripe customer id found for auto top up")
        return False, "No Stripe customer id found"

    amount = topup_required or member.auto_amount

    # Get payment method id for this customer from Stripe
    try:
        pay_list = stripe.PaymentMethod.list(
            customer=member.stripe_customer_id,
            type="card",
        )

        # Use most recent payment if multiple found
        pay_method_id = pay_list.data[0].id

    except stripe.error.InvalidRequestError as error:
        log_event(
            user=member,
            severity="WARN",
            source="Payments",
            sub_source="auto_topup_member",
            message="Error from stripe - see logs",
        )

        logger.warning(f"{member} error retrieving payment method from stripe")
        return _auto_topup_member_handle_failure(error, member, amount)

    # try payment
    try:
        return _auto_topup_member_stripe_transaction(
            amount, member, pay_method_id, payment_type
        )

    except stripe.error.CardError as error:
        return _auto_topup_member_handle_failure(error, member, amount)


def _auto_topup_member_stripe_transaction(amount, member, pay_method_id, payment_type):
    """
    Sub process of auto_topup_member to process the happy path of the stripe transaction working.
    If we fail, we throw a stripe exception and auto_topup_member will invoke the error handling.
    """
    stripe_return = stripe.PaymentIntent.create(
        amount=int(amount * 100),
        currency="aud",
        customer=member.stripe_customer_id,
        payment_method=pay_method_id,
        description=f"Auto Top Up for {member}",
        off_session=True,
        confirm=True,
        metadata={"cobalt_tran_type": "Auto"},
    )

    # It worked so create a stripe record
    payload = stripe_return.charges.data[0]

    stripe_tran = StripeTransaction()
    stripe_tran.description = "Auto Top Up"
    stripe_tran.amount = amount
    stripe_tran.member = member
    stripe_tran.route_code = None
    stripe_tran.route_payload = None
    stripe_tran.stripe_reference = payload.id
    stripe_tran.stripe_method = payload.payment_method
    stripe_tran.stripe_currency = payload.currency
    stripe_tran.stripe_receipt_url = payload.receipt_url
    stripe_tran.stripe_brand = payload.payment_method_details.card.brand
    stripe_tran.stripe_country = payload.payment_method_details.card.country
    stripe_tran.stripe_exp_month = payload.payment_method_details.card.exp_month
    stripe_tran.stripe_exp_year = payload.payment_method_details.card.exp_year
    stripe_tran.stripe_last4 = payload.payment_method_details.card.last4
    stripe_tran.stripe_balance_transaction = payload.balance_transaction
    stripe_tran.last_change_date = timezone.now()
    stripe_tran.status = "Succeeded"
    stripe_tran.save()

    logger.info(f"Auto top up successful for {member}. Amount={amount}")

    # Update members account
    update_account(
        member=member,
        amount=amount,
        description="Payment from %s card **** **** ***** %s Exp %s/%s"
        % (
            payload.payment_method_details.card.brand,
            payload.payment_method_details.card.last4,
            payload.payment_method_details.card.exp_month,
            abs(payload.payment_method_details.card.exp_year) % 100,
        ),
        payment_type=payment_type,
        stripe_transaction=stripe_tran,
    )

    # Notify member
    email_body = (
        f"Auto top up of {GLOBAL_CURRENCY_SYMBOL}{amount:.2f} into your {BRIDGE_CREDITS} "
        f"account was successful.<br><br>"
    )

    # send
    contact_member(
        member=member,
        msg="Auto top up of %s%s successful" % (GLOBAL_CURRENCY_SYMBOL, amount),
        contact_type="Email",
        html_msg=email_body,
        link="/payments",
        subject="Auto top up successful",
    )

    return (
        True,
        "Top up successful. %s%.2f added to your account \
                     from %s card **** **** ***** %s Exp %s/%s"
        % (
            GLOBAL_CURRENCY_SYMBOL,
            amount,
            payload.payment_method_details.card.brand,
            payload.payment_method_details.card.last4,
            payload.payment_method_details.card.exp_month,
            abs(payload.payment_method_details.card.exp_year) % 100,
        ),
    )


def _auto_topup_member_handle_failure(error, member, amount):
    """
    Sub process of auto_topup_member to handle errors when processing the payment
    """
    err = error.error
    logger.error(err.message)
    # Error code will be authentication_required if authentication is needed
    log_event(
        user=member,
        severity="WARN",
        source="Payments",
        sub_source="test_autotopup",
        message="Error from stripe - %s" % err.message,
    )

    msg = "%s Auto Top Up has been disabled." % err.message
    email_body = """We tried to take a payment of $%.2f from your credit card
        but we received this message:
        %s
        Auto Top Up has been disabled for the time being, but you can
        enable it again by clicking below.
        <br><br>
        """ % (
        amount,
        err.message,
    )

    link = reverse("payments:setup_autotopup")

    contact_member(
        member=member,
        msg=msg,
        html_msg=email_body,
        contact_type="Email",
        subject="Auto Top Up Failure",
        link=link,
        link_text="Auto Top Up",
    )
    member.stripe_auto_confirmed = "No"
    member.save()
    return False, "%s Auto Top has been disabled." % err.message


###################################
# org_balance                     #
###################################
def org_balance(organisation):
    """Returns org balance

    Args:
        organisation (organisations.models.Organisation): Organisation object

    Returns:
        float: balance
    """

    # get balance
    last_tran = OrganisationTransaction.objects.filter(organisation=organisation).last()
    balance = last_tran.balance if last_tran else 0.0
    return float(balance)


###################################
# payments_status_summary         #
###################################
def payments_status_summary():
    """Called by utils to show a management summary of how payments is working.

    Args:
        None

    Returns:
        dict: various indicators in a dictionary
    """

    try:
        stripe_latest = StripeTransaction.objects.filter(status="Success").latest(
            "created_date"
        )
        stripe_manual_pending = StripeTransaction.objects.filter(status="Pending")
        stripe_auto_pending = User.objects.filter(stripe_auto_confirmed="Pending")

        if stripe_manual_pending or stripe_auto_pending:  # errors
            status = "Bad"
        else:
            status = "Good"

        payments_indicators = {
            "latest": stripe_latest,
            "manual_pending": stripe_manual_pending,
            "auto_pending": stripe_auto_pending,
            "status": status,
        }

    except StripeTransaction.DoesNotExist:
        payments_indicators = {"status": "Unknown"}

    return payments_indicators


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
    except (IndexError, JSONDecodeError):  # server down or some error
        # raise Http404
        summary = {"IsActive": False, "HomeClubID": 0}

    # Set active to a boolean
    summary["IsActive"] = summary["IsActive"] == "Y"

    # Get home club name
    qry = "%s/club/%s" % (GLOBAL_MPSERVER, summary["HomeClubID"])
    try:
        club = requests.get(qry).json()[0]["ClubName"]
    except (IndexError, JSONDecodeError):  # server down or some error
        club = "Unknown"

    # get balance
    last_tran = (
        MemberTransaction.objects.filter(member=user).order_by("created_date").last()
    )
    balance = last_tran.balance if last_tran else "Nil"
    # get auto top up
    auto_button = user.stripe_auto_confirmed == "On"
    events_list = (
        MemberTransaction.objects.filter(member=user)
        .select_related("member", "other_member")
        .order_by("-created_date")
    )

    return summary, club, balance, auto_button, events_list


def member_to_member_transfer_callback(stripe_transaction=None):
    """Callback for member to member transfers. We have already made the payments, so just let people know.

    We will get a stripe_transaction from the manual payment screen (callback from stripe webhook).
    If we don't get one that is because this was handled already so ignore.

    Three scenarios (doesn't matter if manual or auto top up):

    1. The user had enough funds to pay the other member - emails already sent, stripe_tran = None
    2. The user paid the full amount on their credit card - stripe amount = transfer amount
    3. The user had some funds and paid the rest on their credit card - stripe amt + previous bal = transfer amount

    """

    if not stripe_transaction:
        return

    logger.info(f"Callback received with {stripe_transaction}")

    # Get other member
    # We will have a stripe_transaction that is linked to a member_transaction, that is the member_transaction for
    # this member (the one who paid). The very next transaction in their account will be the outgoing payment.
    this_member_transaction = MemberTransaction.objects.filter(
        stripe_transaction=stripe_transaction
    ).first()
    if not this_member_transaction:
        logger.info(
            f"Could not find matching member transaction for {stripe_transaction}"
        )
        return HttpResponse()

    logger.info(
        f"Found member transaction: {this_member_transaction.id} {this_member_transaction}"
    )

    # Get transaction after this_member_transaction (id>) for this member This will be the other member transaction
    # as these are booked simultaneously, and only moments before this code runs

    other_member_transaction = (
        MemberTransaction.objects.filter(member=this_member_transaction.member)
        .filter(id__gt=this_member_transaction.id)
        .first()
    )

    if not other_member_transaction:
        logger.error(
            f"Could not find matching outgoing member transaction for {stripe_transaction}"
        )
        return HttpResponse()

    if not other_member_transaction.other_member:
        logger.error(f"No other_member found on {other_member_transaction}")
        return HttpResponse()

    # We use the same function in payments API that is used for sufficient funds
    # Note - this could be a partial payment so use the negative of the other_member_transaction,
    # not the stripe_transaction
    notify_member_to_member_transfer(
        stripe_transaction.member,
        other_member_transaction.other_member,
        -other_member_transaction.amount,
        stripe_transaction.description,
    )
    return HttpResponse()
