# Define some constants
from django.db.models import Sum

from accounts.models import User, UnregisteredUser
from club_sessions.models import (
    SessionEntry,
    SessionTypePaymentMethodMembership,
    SessionMiscPayment,
    Session,
)
from cobalt.settings import (
    GLOBAL_ORG,
    ALL_SYSTEM_ACCOUNTS,
    BRIDGE_CREDITS,
    GLOBAL_CURRENCY_SYMBOL,
)
from masterpoints.views import abf_checksum_is_valid
from notifications.notifications_views.core import send_cobalt_email_to_system_number
from organisations.models import ClubLog
from organisations.views.general import get_membership_type_for_players
from payments.models import OrgPaymentMethod, MemberTransaction, UserPendingPayment
from payments.payments_views.core import (
    org_balance,
    update_account,
    update_organisation,
)

PLAYING_DIRECTOR = 1
SITOUT = -1
VISITOR = 0


def bridge_credits_for_club(club):
    """return the bridge credits payment method for a club"""

    return OrgPaymentMethod.objects.filter(
        active=True, organisation=club, payment_method="Bridge Credits"
    ).first()


def iou_for_club(club):
    """return the IOU payment method for a club"""

    return OrgPaymentMethod.objects.filter(
        active=True, organisation=club, payment_method="IOU"
    ).first()


def load_session_entry_static(session, club):
    """Sub of tab_session_htmx. Load the data we need to be able to process the session tab"""

    # Get the entries for this session
    session_entries = SessionEntry.objects.filter(session=session)

    # Map to Users or UnregisteredUsers

    # Get system numbers
    system_number_list = session_entries.values_list("system_number")

    # Get Users and UnregisteredUsers
    users = User.objects.filter(system_number__in=system_number_list)
    un_regs = UnregisteredUser.objects.filter(system_number__in=system_number_list)

    # Convert to a dictionary
    mixed_dict = {}

    for user in users:
        user.is_user = True
        mixed_dict[user.system_number] = {
            "type": "User",
            "value": user,
            "icon": "account_circle",
        }

    # Add unregistered to dictionary
    for un_reg in un_regs:
        un_reg.is_un_reg = True
        mixed_dict[un_reg.system_number] = {
            "type": "UnregisteredUser",
            "value": un_reg,
            "icon": "stars",
        }

    # Get memberships
    membership_type_dict = get_membership_type_for_players(system_number_list, club)

    # Add visitor
    membership_type_dict[VISITOR] = "Guest"

    # Load session fees
    session_fees = get_session_fees_for_club(club)

    return session_entries, mixed_dict, session_fees, membership_type_dict


def get_session_fees_for_club(club):
    """return session fees as a dictionary. We use the name of the membership as the key, not the number

    e.g. session_fees = {"Standard": {"EFTPOS": 5, "Cash": 12}}

    """

    fees = SessionTypePaymentMethodMembership.objects.filter(
        session_type_payment_method__session_type__organisation=club
    )

    session_fees = {}
    for fee in fees:
        membership_name = "Guest" if fee.membership is None else fee.membership.name
        if membership_name not in session_fees:
            session_fees[membership_name] = {}
        session_fees[membership_name][
            fee.session_type_payment_method.payment_method.payment_method
        ] = fee.fee

    return session_fees


def get_extras_as_total_for_session_entries(
    session, paid_only=False, unpaid_only=False
):
    """get the total amount of extras for each session entry as a dictionary

    paid_only - only included total for extras that have been paid for
    unpaid_only - only included total for extras that have not been paid for

    """
    extras_qs = (
        SessionMiscPayment.objects.filter(session_entry__session=session)
        .values("session_entry")
        .annotate(extras=Sum("amount"))
    )

    if paid_only:
        extras_qs = extras_qs.filter(payment_made=True)

    if unpaid_only:
        extras_qs = extras_qs.filter(payment_made=False)

    # convert to dict
    return {item["session_entry"]: float(item["extras"]) for item in extras_qs}


def get_extras_for_session_entries(session_entries):
    """get the extras associated with a queryset of SessionEntries"""

    session_entries_list = session_entries.values_list("id", flat=True)
    extras = SessionMiscPayment.objects.filter(
        session_entry__in=session_entries_list
    ).values("session_entry", "amount")
    extras_dict = {}
    for extra in extras:
        if extra["session_entry"] not in extras_dict:
            extras_dict[extra["session_entry"]] = extra["amount"]
        else:
            extras_dict[extra["session_entry"]] += extra["amount"]

    return extras_dict


def augment_session_entries_process_entry(
    session_entry, mixed_dict, membership_type_dict, extras_dict, valid_payment_methods
):
    """sub of _augment_session_entries to handle a single session entry"""

    # table
    if session_entry.pair_team_number % 2 == 0:
        session_entry.table_colour = "even"
    else:
        session_entry.table_colour = "odd"

    # Add User or UnregisterUser to the entry and note the player_type
    if session_entry.system_number == SITOUT:
        # Sit out
        session_entry.player_type = "NotRegistered"
        session_entry.icon = "hourglass_empty"
        session_entry.player = {"full_name": "Sitout", "first_name": "Sitout"}
        icon_text = "There is nobody at this position"
    elif session_entry.system_number == PLAYING_DIRECTOR:
        # Playing Director
        session_entry.player_type = "NotRegistered"
        session_entry.icon = "local_police"
        session_entry.player = {
            "full_name": "PLAYING DIRECTOR",
            "first_name": "DIRECTOR",
        }
        icon_text = "Playing Director"
    elif session_entry.system_number == VISITOR:
        # Visitor with no ABF number
        session_entry.player_type = "NotRegistered"
        session_entry.icon = "handshake"
        session_entry.player = {
            "full_name": session_entry.player_name_from_file.title(),
            "first_name": session_entry.player_name_from_file.split(" ")[0].title(),
        }
        icon_text = f"Non-{GLOBAL_ORG} Member"
    elif session_entry.system_number in mixed_dict:
        session_entry.player = mixed_dict[session_entry.system_number]["value"]
        session_entry.player_type = mixed_dict[session_entry.system_number]["type"]
        session_entry.icon = mixed_dict[session_entry.system_number]["icon"]
        icon_text = f"{session_entry.player.first_name} is "

    else:
        session_entry.player_type = "NotRegistered"
        session_entry.icon = "error"
        session_entry.player = {"full_name": "Unknown"}
        icon_text = "This person is "

    # membership
    if session_entry.system_number == SITOUT:
        # Sit out
        session_entry.membership = "Guest"
    elif session_entry.system_number in membership_type_dict:
        # This person is a member
        session_entry.membership = membership_type_dict[session_entry.system_number]
        session_entry.membership_type = "member"
        session_entry.icon_colour = "primary"
        if session_entry.system_number not in [SITOUT, PLAYING_DIRECTOR, VISITOR]:
            icon_text += f"a {session_entry.membership} member."
    else:
        # Not a member
        session_entry.membership = "Guest"
        if session_entry.system_number not in [SITOUT, PLAYING_DIRECTOR, VISITOR]:
            icon_text += "a Guest."
        if session_entry.system_number >= 0 and abf_checksum_is_valid(
            session_entry.system_number
        ):
            session_entry.membership_type = "Valid Number"
            session_entry.icon_colour = "warning"
        else:
            session_entry.membership_type = "Invalid Number"
            session_entry.icon_colour = "dark"

    # valid payment method. In list of valid is fine, or simple not set is fine too
    if session_entry.payment_method:
        session_entry.payment_method_is_valid = (
            session_entry.payment_method.payment_method in valid_payment_methods
        )
    else:
        session_entry.payment_method_is_valid = True

    # Add icon text
    session_entry.icon_text = icon_text

    # Add extras
    session_entry.extras = extras_dict.get(session_entry.id, 0)

    return session_entry


def augment_session_entries(
    session_entries, mixed_dict, membership_type_dict, session_fees, club
):
    """Sub of tab_Session_htmx. Adds extra values to the session_entries for display by the template

    Players can be:
        Users
        UnregisteredUsers
        Nothing

        If Nothing, they can have a valid ABF number, an invalid ABF number or no ABF number

    Their relationship with the club can be:
        Member
        Non-member

    """

    # The payment method may no longer be valid, we want to flag this
    valid_payment_methods = OrgPaymentMethod.objects.filter(
        organisation=club, active=True
    ).values_list("payment_method", flat=True)

    # Get any extra payments as a dictionary
    extras_dict = get_extras_for_session_entries(session_entries)

    # Now add the object to the session list, also add colours for alternate tables
    for session_entry in session_entries:
        session_entry = augment_session_entries_process_entry(
            session_entry,
            mixed_dict,
            membership_type_dict,
            extras_dict,
            valid_payment_methods,
        )

    # work out payment method and if user has sufficient funds
    return calculate_payment_method_and_balance(session_entries, session_fees, club)


def calculate_payment_method_and_balance(session_entries, session_fees, club):
    """work out who can pay by bridge credits and if they have enough money"""

    # First build list of users who are bridge credit eligible
    bridge_credit_users = []
    for session_entry in session_entries:
        if session_entry.player_type == "User" and session_entry.system_number not in [
            ALL_SYSTEM_ACCOUNTS
        ]:
            bridge_credit_users.append(session_entry.system_number)

    # Now get their balances
    balances = {
        member_transaction.member: member_transaction.balance
        for member_transaction in MemberTransaction.objects.filter(
            member__system_number__in=bridge_credit_users
        )
    }

    bridge_credit_payment_method = OrgPaymentMethod.objects.filter(
        organisation=club, payment_method=BRIDGE_CREDITS, active=True
    ).first()

    # Go through and add balance to session entries
    for session_entry in session_entries:
        if session_entry.player_type == "User":
            # if not in balances then it is zero
            session_entry.balance = balances.get(session_entry.player, 0)

            # Only change payment method to Bridge Credits if not set to something already
            if not session_entry.payment_method:
                session_entry.payment_method = bridge_credit_payment_method

        # fee due
        if (
            session_entry.payment_method
            and not session_entry.fee
            and not session_entry.system_number == PLAYING_DIRECTOR
        ):
            session_entry.fee = session_fees[session_entry.membership][
                session_entry.payment_method.payment_method
            ]

        session_entry.save()

        if session_entry.fee:
            session_entry.total = session_entry.fee + session_entry.extras
        else:
            session_entry.total = "NA"

    return session_entries


def handle_iou_changes(payment_method, club, session_entry, administrator):
    """handle the payment type toggling between IOU and something else"""

    # Check for turning on
    if payment_method.payment_method == "IOU":
        handle_iou_changes_on(club, session_entry, administrator)

    # Check for turning off
    if session_entry.payment_method.payment_method == "IOU":
        handle_iou_changes_off(club, session_entry)


def handle_iou_changes_on(club, session_entry, administrator):
    """Handle turning on an IOU"""

    # For safety ensure we don't duplicate
    user_pending_payment, _ = UserPendingPayment.objects.get_or_create(
        organisation=club,
        system_number=session_entry.system_number,
        session_entry=session_entry,
        amount=session_entry.fee,
        description=session_entry.session.description,
    )
    user_pending_payment.save()

    subject = f"Pending Payment to {club}"
    message = f"""
    {administrator.full_name} has recorded you as entering {session_entry.session} but not paying.
    That is fine, you can pay later.
    <br><br>
    The amount owing is {GLOBAL_CURRENCY_SYMBOL}{session_entry.fee}.
    <br><br>
    If you believe this to be incorrect please contact {club} directly in the first instance.
    """

    send_cobalt_email_to_system_number(
        session_entry.system_number,
        subject,
        message,
        club=club,
        administrator=administrator,
    )

    session_entry.is_paid = True
    session_entry.save()


def handle_iou_changes_off(club, session_entry):
    """Turn off using an IOU"""

    print("Off")

    UserPendingPayment.objects.filter(
        organisation=club,
        system_number=session_entry.system_number,
        session_entry=session_entry,
    ).delete()


def handle_bridge_credit_changes(
    payment_method, club, session_entry, director, message
):
    """When the director changes payment method from bridge credit to something else, we need to handle refunds
    if payment already made.

    If they change from something else to Bridge Credits then we need to change the status of the session.

    Returns:
        status(boolean): is it okay to continue, True/False
        message(str): message to return to user, can be empty

    """

    bridge_credit_payment_method = bridge_credits_for_club(club)

    if (
        session_entry.payment_method != bridge_credit_payment_method
        and payment_method != bridge_credit_payment_method
    ):
        # No bridge credits involved (not old payment method or new)
        return True, message

    if (
        session_entry.payment_method == bridge_credit_payment_method
        and session_entry.is_paid
    ):
        return handle_bridge_credit_changes_refund(club, session_entry, director)

    if payment_method == bridge_credit_payment_method:
        # New payment method is bridge credits. Force status to be pending bridge credits
        session_entry.session.status = Session.SessionStatus.DATA_LOADED
        session_entry.session.save()

        # Mark entry as unpaid - don't drop paid extras though
        session_entry.is_paid = False
        # for misc_payments in SessionMiscPayment.objects.filter(
        #         session_entry=session_entry, payment_method=bridge_credit_payment_method
        # ):
        #     if misc_payments.payment_made:
        #         session_entry.amount_paid += misc_payments.amount
        session_entry.save()
        return True, message

    else:
        # Was bridge credits, but isn't now. Mark as unpaid
        session_entry.is_paid = False
        session_entry.save()


def handle_bridge_credit_changes_refund(club, session_entry, director):
    # Refund needed
    if org_balance(club) < session_entry.fee:
        return False, "Club has insufficient funds for this refund"

    player = User.objects.filter(system_number=session_entry.system_number).first()

    update_account(
        member=player,
        amount=session_entry.fee,
        description=f"{BRIDGE_CREDITS} returned for {session_entry.session}",
        payment_type="Refund",
        organisation=club,
    )

    update_organisation(
        organisation=club,
        amount=-session_entry.fee,
        description=f"{BRIDGE_CREDITS} returned for {session_entry.session}",
        payment_type="Refund",
        member=player,
    )

    # log it
    ClubLog(
        organisation=club,
        actor=director,
        action=f"Refunded {player} {GLOBAL_CURRENCY_SYMBOL}{session_entry.fee:.2f} for session",
    ).save()

    return True, "Player refunded"


def session_totals_calculations(
    session, session_entries, session_fees, membership_type_dict
):
    """sub of session_totals_htmx to build dict of totals"""

    # initialise totals
    totals = {
        "tables": 0,
        "players": 0,
        "unknown_payment_methods": 0,
        "bridge_credits_due": 0,
        "bridge_credits_received": 0,
        "other_methods_due": 0,
        "other_methods_received": 0,
    }

    # go through entries and update totals
    for session_entry in session_entries:

        # ignore missing players
        if session_entry.system_number == SITOUT:
            continue

        totals["players"] += 1

        # handle unknown payment methods
        if not session_entry.payment_method:
            totals["unknown_payment_methods"] += 1
            continue

        # we only store system_number on the session_entry. Need to look up amount due via membership type for
        # this system number and the session_fees for this club for each membership type

        # It is also possible that the static data has changed since this was created, so we need to
        # handle the session_fees not existing for this payment_method

        # Get membership for user, if not found then this will be a Guest
        membership_for_this_user = membership_type_dict.get(
            session_entry.system_number, "Guest"
        )

        if session_entry.fee:
            # If fee is set then use that
            this_fee = session_entry.fee
        else:
            # Otherwise, try to look it up
            try:
                this_fee = session_fees[membership_for_this_user][
                    session_entry.payment_method.payment_method
                ]
            except KeyError:
                # if that fails default to 0 - will mean the static has changed since we set the payment_method
                # and this payment method is no longer in use. 0 seems a good default
                this_fee = 0

        # Update totals
        if session_entry.payment_method.payment_method == BRIDGE_CREDITS:
            totals["bridge_credits_due"] += this_fee
            if session_entry.is_paid:
                totals["bridge_credits_received"] += session_entry.fee
        else:
            totals["other_methods_due"] += this_fee
            if session_entry.is_paid:
                totals["other_methods_received"] += session_entry.fee

    totals["tables"] = totals["players"] / 4

    return totals


def handle_change_secondary_payment_method(
    old_method, new_method, session, club, administrator
):
    """make changes when the secondary payment method is updated"""

    session_entries = SessionEntry.objects.filter(
        session=session, payment_method=old_method
    ).exclude(system_number__in=[PLAYING_DIRECTOR, SITOUT])
    for session_entry in session_entries:
        session_entry.payment_method = new_method
        session_entry.save()

        # Handle IOUs
        if new_method.payment_method == "IOU":
            handle_iou_changes_on(club, session_entry, administrator)

        if old_method.payment_method == "IOU":
            handle_iou_changes_off(club, session_entry)

    if session_entries:
        message = f"Updated {len(session_entries)} player payment methods."
    else:
        message = "Form saved. No player payment methods were changed."

    return message


def handle_change_additional_session_fee_reason(old_reason, new_reason, session, club):
    """Handle the settings being changed for additional fees - change the reason"""

    session_entries = SessionEntry.objects.filter(session=session).exclude(
        system_number__in=[PLAYING_DIRECTOR, SITOUT]
    )

    for session_entry in session_entries:
        SessionMiscPayment.objects.filter(
            session_entry=session_entry,
            description=old_reason,
        ).update(description=new_reason)


def handle_change_additional_session_fee(old_fee, new_fee, session, club, old_reason):
    """Handle the settings being changed for additional fees"""

    bridge_credits = bridge_credits_for_club(club)
    iou = iou_for_club(club)

    message = ""

    session_entries = SessionEntry.objects.filter(session=session).exclude(
        system_number__in=[PLAYING_DIRECTOR, SITOUT]
    )

    for session_entry in session_entries:

        if old_fee == 0:
            # Create new entries from scratch
            SessionMiscPayment(
                session_entry=session_entry,
                description=session.additional_session_fee_reason,
                payment_method=session_entry.payment_method,
                amount=new_fee,
            ).save()

        elif new_fee == 0:
            # Delete entries without bridge credits or ious
            SessionMiscPayment.objects.filter(session_entry=session_entry).filter(
                description=old_reason
            ).exclude(payment_method__in=[bridge_credits, iou]).delete()

            # Handle bridge credits and IOUs
            if (
                SessionMiscPayment.objects.filter(session_entry=session_entry)
                .filter(description=old_reason)
                .filter(payment_method__in=[bridge_credits, iou])
                .exists()
            ):
                message = f" Some entries have paid with {BRIDGE_CREDITS} or IOUs. You need to handle these manually."
            else:
                message = "Additional fees removed."

        else:
            # Update entries without bridge credits or ious
            SessionMiscPayment.objects.filter(session_entry=session_entry).filter(
                description=old_reason
            ).exclude(payment_method__in=[bridge_credits, iou]).update(
                amount=new_fee, payment_made=False
            )

            # Handle bridge credits and IOUs
            if (
                SessionMiscPayment.objects.filter(session_entry=session_entry)
                .filter(description=old_reason)
                .filter(payment_method__in=[bridge_credits, iou])
                .exists()
            ):
                message = f" Some entries have paid with {BRIDGE_CREDITS} or IOUs. You need to handle these manually."
            else:
                message = "Additional fees changed."

    return message
