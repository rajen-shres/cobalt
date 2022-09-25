from django.db.transaction import atomic
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404

from accounts.accounts_views.core import (
    get_users_or_unregistered_users_from_system_number_list,
)
from accounts.models import User
from club_sessions.models import Session, SessionEntry, SessionType
from organisations.decorators import check_club_menu_access
from organisations.models import ClubLog
from organisations.views.general import org_balance
from payments.models import OrgPaymentMethod, UserPendingPayment
from payments.payments_views.core import update_organisation, update_account


@check_club_menu_access()
def refresh_sessions_tab(request, club, message=""):
    """The sessions tab hangs after we upload a file. This refreshes the whole tab.
    Also called by the delete session function.
    """

    return render(
        request,
        "organisations/club_menu/sessions.html",
        {"club": club, "message": message},
    )


@check_club_menu_access(check_sessions=True)
def delete_session_htmx(request, club):
    """Handle request to delete a session"""

    # Get session
    session = get_object_or_404(Session, pk=request.POST.get("session_id"))

    # Check valid
    if session.session_type.organisation != club:
        return HttpResponse("This session does not belong to this club")

    # See if anyone has paid using bridge credits
    bridge_credits = OrgPaymentMethod.objects.filter(
        active=True, organisation=club, payment_method="Bridge Credits"
    ).first()

    payments = SessionEntry.objects.filter(
        session=session, payment_method=bridge_credits
    ).filter(is_paid=True)

    # See if we have any IOUs
    ious = UserPendingPayment.objects.filter(
        organisation=club,
        session_entry__session=session,
    )

    # See if this is the confirm option
    if "really_delete" in request.POST:
        message = _cancel_and_refund_bridge_credits_and_ious(
            request, payments, ious, club, session
        )
        return refresh_sessions_tab(request, message=message)

    # Get names for people rather than system numbers
    ious_system_numbers = ious.values_list("system_number")
    ious_names = User.objects.filter(system_number__in=ious_system_numbers)

    # Add name to session_entries
    system_number_list = payments.values_list("system_number", flat=True)

    users_dict = get_users_or_unregistered_users_from_system_number_list(
        system_number_list
    )

    for payment in payments:
        payment.full_name = users_dict[payment.system_number]["value"]

    return render(
        request,
        "organisations/club_menu/sessions/delete_session_htmx.html",
        {
            "club": club,
            "session": session,
            "payments": payments,
            "ious_names": ious_names,
        },
    )


@atomic()
def _cancel_and_refund_bridge_credits_and_ious(request, payments, ious, club, session):
    """sub of delete_session_htmx to refund money to people who paid for this session with bridge credits
    and also cancel any IOUs for this session"""

    user_message = f"Refund for cancelled session({session.description}) at {club}"
    refund_count = 0

    # First check if club has sufficient funds for this
    total = sum(payment.fee for payment in payments if payment.is_paid)
    if total > org_balance(club):
        return "This club has an insufficient balance to make these refunds"

    # Now go through and process refunds
    for payment in payments:

        # Double check
        if not payment.is_paid:
            continue

        member = User.objects.filter(system_number=payment.system_number).first()
        refund_count += 1

        update_organisation(
            organisation=club,
            member=member,
            amount=-payment.fee,
            description=f"Refund for cancelled session {session.description} by {request.user}",
            payment_type="Refund",
        )

        update_account(
            organisation=club,
            amount=payment.fee,
            description=user_message,
            payment_type="Refund",
            member=member,
        )

    # Delete the IOUs
    iou_count = ious.count()
    ious.delete()

    # log it
    if refund_count > 0:
        action = f"Cancelled session '{session.description}'. Refunded {refund_count} member(s)."
        message = f"Session deleted. {refund_count} refunds made."
    else:
        action = f"Cancelled session '{session.description}'. No refunds required."
        message = "Session deleted"

    if iou_count > 0:
        action = f"{action} {iou_count} IOU(s) cancelled."
        message = f"{message} {iou_count} IOU(s) cancelled."

    ClubLog(
        organisation=club,
        actor=request.user,
        action=action,
    ).save()

    # Delete all session entries
    SessionEntry.objects.filter(session=session).delete()

    # Delete session
    session.delete()

    return message


@check_club_menu_access(check_sessions=True)
def club_menu_tab_sessions_sub_htmx(request, club):
    """this just loads the sessions tab in the club menu, but with some values"""

    # if there are more than 1 session type, then let user choose when they create a new session
    session_types = SessionType.objects.filter(organisation=club)
    if len(session_types) == 1:
        session_types = None

    return render(
        request,
        "organisations/club_menu/sessions/session_tab.html",
        {"club": club, "session_types": session_types},
    )
