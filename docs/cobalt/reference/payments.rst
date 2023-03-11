:orphan:

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

.. image:: ../../images/heavy-dollar-sign.png
  :width: 200
  :alt: Cobalt Dollar Symbol

:doc:`../how_to/using_references`

====================
Payments Application
====================

.. note::
    This page has the documentation on how to use this application (externally provided APIs etc). If you are looking for
    information on how it works internally, you can find that in :doc:`./payments_support`.

**************
Module Purpose
**************

Payments handles anything related to money within Cobalt. It is used by the
other modules to facilitate and track payments and as such is primarily an
internal service function, however it also has some interaction directly with
users to view statements and manage auto tops as well as member-to-member
transfers.

Payments is tightly couple with Stripe. This was a deliberate design decision as
supporting multiple payment engines is an administrative nightmare for payment staff
so it is assumed that only one payment gateway will every be used. If a second is
required then the code will need to be refactored to include this abstraction.

.. _payments_apis_label:

********
APIs
********

------------
User Actions
------------
This section has functions related to user payments.

Get a User's Balance
====================

:func:`~payments.payments_views.core.get_balance`

.. code-block::

    from payments.payments_views.core import get_balance

    >>> get_balance(user)
    100.0

Get a User's Balance and Last Top Up Date
=========================================

:func:`~payments.payments_views.core.get_balance_detail`

.. code-block::

    from payments.payments_views.core import get_balance_detail

    >>> get_balance_detail(user)
    {'balance': Decimal('100.00'),
     'balance_num': Decimal('100.00'),
     'last_top_up': datetime.datetime(2022, 4, 9, 11, 34, 5, 781492, tzinfo=<UTC>)}

Update a User's Account
=======================

:func:`~payments.payments_views.core.update_account`
    You cannot directly change a user's balance except by applying a transaction to their account.
    Transactions should have either Stripe, a user or an organisation as the counterparty.


.. code-block::

    from payments.payments_views.core import update_account

    >>> update_account(member=user, amount=50.45, description="Birthday Present", other_member=me)

Attempt A Payment for a Logged in User
======================================

:func:`~payments.payments_views.payments_api.payment_api_interactive`
    When you have a user trying to do something that involves a payment, you can call ``payment_api_interactive``
    to make the payment attempt. If the user has sufficient funds then the payment will be processed and you
    can optionally receive a callback (for success or failure). If the user doesn't have sufficient funds but is
    set up for auto top up, then that will be attempted next. Finally, if auto top up is not setup or fails,
    the user will be taken to the manual top up screen to make a credit card payment.

    Note: callbacks are currently hardcoded. to add a new callback you need to
    update :func:`payments.payments_views.core.callback_router`.


.. code-block::

    from payments.payments_views.payments_api import payment_api_interactive

    def my_view(request):

    return payment_api_interactive(
        request=request,
        member=request.user,
        description="Congress Entry",
        amount=50.25,
        route_code="EVT",
        route_payload="My identifier",
        next_url=reverse("events:enter_event_success"),
        payment_type="Entry to an event",
        book_internals=False,
    )

``Request``, ``member``, ``description`` and ``amount`` are fairly obvious. ``payment_type`` needs to be a valid type of payment.
In a future release this will be changed to an enum.

Whenever you use ``payment_api_interactive`` there will be a user on the end of this who needs to be interacted with.

Attempt A Payment for a User Who is Not Logged In
=================================================

:func:`~payments.payments_views.payments_api.payment_api_batch`
    If the user you are making this payment for is not attached to this session, you can use this function instead.

.. code-block::

    from payments.payments_views.payments_api import payment_api_batch

    if payment_api_batch(
        member=user,
        description="Party drinks",
        amount=3943.99,
        organisation=club,
        payment_type="Miscellaneous",
        book_internals=True,
    ):
        # Handle success
    else:
        # Handle failure

--------------------
Organisation Actions
--------------------
This section has functions related to organisation payments.

Get an Organisation's Balance
=============================

:func:`~payments.payments_views.core.org_balance`

.. code-block::

    from payments.payments_views.core import org_balance

    >>> get_balance(club)
    400.0

Update an Organisation's Account
=================================

:func:`~payments.payments_views.core.update_organisation`
    To update an organisations account, you can use ``update_organisation``.
    Transactions should have either Stripe, a user or another organisation as the counterparty.

.. code-block::

    from payments.payments_views.core import update_organisation

    update_organisation(
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

**************
GL Codes
**************

.. WARNING::
   This is currently a discussion section. Change this to factual documentation once the changes are made.

OrganisationTransactions have extra fields to track the purpose of the transaction. These are,
rather incorrectly, internally labelled as GL Codes (General Ledger codes) as they are likely to ultimately
end up being used in a similar way to GL codes by applications that take date feeds from
Cobalt.

The structure of the fields is hierarchical. All fields are associated with a single organisation.

    gl_transaction_type (choice field)
        Top level. Effectively maps to the Cobalt application, currently just Congress or Session.
    gl_category (text 50)
        For a congress, this is the congress series name. For a session this is the session type.
        We only record the name as it stands when this is created, we don't link to the underlying
        items.
    gl_sub_category (text 50)
        For a congress, this is the event. For a session it is the name of the session.
    gl_series (integer)
        For a congress, this is the year. For a session, this is a sequential number.

--------------
Examples
--------------

.. list-table:: Examples of Codes
   :widths: 50 50 50 25
   :header-rows: 1

   * - Transaction Type
     - Category
     - Sub Category
     - Series
   * - Congress
     - NSBC Easter Congress
     - Open Pairs
     - 2023
   * - Congress
     - NSBC Easter Congress
     - Restricted Teams
     - 2023
   * - Congress
     - NSBC Easter Congress
     - Open Pairs
     - 2024
   * - Congress
     - NSBC Easter Congress
     - Restricted Teams
     - 2024
   * - Session
     - Duplicate
     - EL Tue 1:30pm Rookie
     - 491
   * - Session
     - Duplicate
     - EL Tue 1:30pm Rookie
     - 492
   * - Session
     - Duplicate
     - EL Tue 1:30pm Rookie
     - 493
   * - Session
     - Duplicate
     - RB Sat 10am Open
     - 53
   * - Session
     - Duplicate
     - RB Sat 10am Open
     - 54

-----------------------
Potential Issues / Work
-----------------------

Congresses
==========

Congresses are fairly straightforward. We can get all of the data we need just from the
event and the congress. We don't currently capture this information but it is a manageable
change to add it.

We will record only the names of things as they are at the time the entry is made. This means
there is no linkage back to the event, especially if it changes with time. For example,
if one year it is "Honda Welcome Pairs" and the next year it is "Nissan Opening Pairs" then we
won't know they are the same event. That should be easy enough to handle in any downstream
systems, and isn't really a problem for Cobalt.

Sessions
========

We already store the session on the OrganisationTransaction. We can access the session data and
save the GL info from this. The main problem is the sub-category which comes in as free format
text. For the CompScore files we get the session description either from the file or from the
file name. This seems reasonably reliable but needs manipulation to remove dates. It is not an
ideal solution but we can also allow the director to change the sub-category on the settings
page. The series can be generated.

Reporting
==========

If we have the data available, as described above, we should be able to report in a number of ways.
We can summarise at the category level (mostly for congresses) or the sub-category level (for
congresses by event or sessions by session type such as Tuesday Open etc). We can also summarise
at the series level for sessions which will show individual sessions.

