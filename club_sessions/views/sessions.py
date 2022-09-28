from django.db.models import Max
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from accounts.views.core import (
    get_user_or_unregistered_user_from_system_number,
)
from accounts.models import User, UnregisteredUser
from cobalt.settings import (
    BRIDGE_CREDITS,
    GLOBAL_CURRENCY_SYMBOL,
    ALL_SYSTEM_ACCOUNTS,
)
from organisations.models import (
    Organisation,
    MemberMembershipType,
    MiscPayType,
)
from organisations.views.club_menu_tabs.finance import pay_member_from_organisation
from payments.models import OrgPaymentMethod, UserPendingPayment
from payments.views.payments_api import payment_api_batch

from rbac.views import rbac_forbidden
from rbac.core import rbac_user_has_role
from .core import (
    SITOUT,
    bridge_credits_for_club,
    iou_for_club,
    load_session_entry_static,
    get_extras_as_total_for_session_entries,
    augment_session_entries,
    calculate_payment_method_and_balance,
    handle_iou_changes,
    handle_iou_changes_on,
    handle_iou_changes_off,
    handle_bridge_credit_changes,
    session_totals_calculations,
    handle_change_secondary_payment_method,
    handle_change_additional_session_fee_reason,
    handle_change_additional_session_fee,
    get_summary_table_data,
    get_allowed_payment_methods,
    get_table_view_data,
    process_bridge_credits,
    add_table,
    refund_bridge_credit_for_extra,
    pay_bridge_credit_for_extra,
    recalculate_session_status,
    handle_bridge_credit_changes_refund,
)
from .decorators import user_is_club_director

from club_sessions.forms import SessionForm, UserSessionForm
from club_sessions.models import (
    Session,
    SessionEntry,
    SessionTypePaymentMethodMembership,
    SessionMiscPayment,
)


@login_required()
def new_session(request, club_id):
    """Set up a new bridge session for a club. Normally we import a file, so this won't be used much."""

    club = get_object_or_404(Organisation, pk=club_id)

    club_role = f"club_sessions.sessions.{club.id}.edit"
    if not rbac_user_has_role(request.user, club_role):
        return rbac_forbidden(request, club_role)

    # Set up form values
    director_name = request.user.full_name

    # Load form
    session_form = SessionForm(
        request.POST or None, club=club, initial={"director": request.user}
    )

    if request.method == "POST" and session_form.is_valid():
        session = session_form.save(commit=False)
        session.club = club
        session.save()
        return redirect("club_sessions:manage_session", session_id=session.id)
    else:
        print(session_form.errors)

    return render(
        request,
        "club_sessions/new/new_session.html",
        {
            "club": club,
            "session_form": session_form,
            "director_name": director_name,
            "new_or_edit": "new",
        },
    )


@login_required()
def manage_session(request, session_id):
    """Main page to manage a club session after it has been created"""

    session = get_object_or_404(Session, pk=session_id)

    club = get_object_or_404(Organisation, pk=session.session_type.organisation.id)

    club_role = f"club_sessions.sessions.{club.id}.edit"
    if not rbac_user_has_role(request.user, club_role):
        return rbac_forbidden(request, club_role)

    has_session_entries = SessionEntry.objects.filter(session=session).exists()

    return render(
        request,
        "club_sessions/manage/manage_session.html",
        {"club": club, "session": session, "has_session_entries": has_session_entries},
    )


@user_is_club_director()
def tab_settings_htmx(request, club, session):
    """Edit fields that were set up when the session was started"""

    message = ""

    if "save_settings" in request.POST:
        session_form = SessionForm(request.POST, club=club, instance=session)

        # Save old values in case we need them below
        old_payment_method = session.default_secondary_payment_method
        old_additional_session_fee = session.additional_session_fee
        old_additional_session_fee_reason = session.additional_session_fee_reason

        if session_form.is_valid():
            session = session_form.save()
            message = "Session Updated"

            if "additional_session_fee" in session_form.changed_data:
                message += handle_change_additional_session_fee(
                    old_fee=old_additional_session_fee,
                    new_fee=session_form.cleaned_data["additional_session_fee"],
                    session=session,
                    club=club,
                    old_reason=old_additional_session_fee_reason,
                )

            if "additional_session_fee_reason" in session_form.changed_data:
                handle_change_additional_session_fee_reason(
                    old_additional_session_fee_reason,
                    session.additional_session_fee_reason,
                    session,
                    club,
                )

            if "default_secondary_payment_method" in session_form.changed_data:
                message += handle_change_secondary_payment_method(
                    old_method=old_payment_method,
                    new_method=session_form.cleaned_data[
                        "default_secondary_payment_method"
                    ],
                    session=session,
                    club=club,
                    administrator=request.user,
                )
        else:
            print(session_form.errors)

    session_form = SessionForm(club=club, instance=session)

    director_name = f"{session.director}"

    response = render(
        request,
        "club_sessions/manage/settings_htmx.html",
        {
            "session_form": session_form,
            "club": club,
            "session": session,
            "message": message,
            "director_name": director_name,
        },
    )

    # Reload sessions tab if we change anything
    if "save_settings" in request.POST:
        response["HX-Trigger"] = "reload_sessions"

    return response


@user_is_club_director()
def tab_session_htmx(request, club, session, message="", bridge_credit_failures=None):
    """present the main session tab for the director

    We have 3 different views (Summary, Detail, Table) but we generate them all from this function.

    That means there are some things calculated that aren't needed for a view, but it keeps it simple.

    """

    if bridge_credit_failures is None:
        bridge_credit_failures = []

    # load static
    (
        session_entries,
        mixed_dict,
        session_fees,
        membership_type_dict,
    ) = load_session_entry_static(session, club)

    # augment the session_entries
    session_entries = augment_session_entries(
        session_entries, mixed_dict, membership_type_dict, session_fees, club
    )

    # get payment methods for this club
    payment_methods = OrgPaymentMethod.objects.filter(organisation=club, active=True)

    # Which template to use - summary, detail or table. Default is summary.
    view_type = request.POST.get("view_type", "summary")
    view_options = {
        "summary": "club_sessions/manage/session_summary_view_htmx.html",
        "detail": "club_sessions/manage/session_detail_view_htmx.html",
        "table": "club_sessions/manage/session_table_view_htmx.html",
    }
    template = view_options[view_type]

    if view_type == "detail":
        # Too hard for the template, so set up allowed payment methods for dropdown in python
        session_entries = get_allowed_payment_methods(
            session_entries, session, payment_methods
        )

    if view_type == "summary":
        # get summary data
        payment_summary = get_summary_table_data(
            session, session_entries, mixed_dict, membership_type_dict
        )
    else:
        payment_summary = {}

    if view_type == "table":
        # Handle table view
        table_list, table_status = get_table_view_data(session, session_entries)
    else:
        table_list = {}
        table_status = {}

    return render(
        request,
        template,
        {
            "club": club,
            "session": session,
            "session_entries": session_entries,
            "table_list": table_list,
            "table_status": table_status,
            "payment_methods": payment_methods,
            "payment_summary": payment_summary,
            "message": message,
            "bridge_credit_failures": bridge_credit_failures,
        },
    )


def _edit_session_entry_handle_post(request, club, session_entry):
    """Sub for edit_session_entry_htmx to handle the form being posted"""

    message = "Data saved"

    form = UserSessionForm(request.POST, club=club, session_entry=session_entry)
    if not form.is_valid():
        print(form.errors)
        return form, "There were errors on the form"

    # get user type
    is_user = request.POST.get("is_user")
    is_un_reg = request.POST.get("is_un_reg")

    # Handle session data
    session_entry.fee = form.cleaned_data["fee"]
    payment_method = OrgPaymentMethod.objects.get(
        pk=form.cleaned_data["payment_method"]
    )

    # Handle player being changed
    new_user_id = form.cleaned_data["player_no"]
    system_number = None
    if new_user_id:
        if is_user:
            system_number = User.objects.get(pk=new_user_id).system_number
        elif is_un_reg:
            system_number = UnregisteredUser.objects.get(pk=new_user_id).system_number
    if system_number:
        session_entry.system_number = system_number

    # Handle IOUs and bridge_credits
    if "payment_method" in form.changed_data:
        handle_iou_changes(payment_method, club, session_entry, request.user)

        # Handle bridge credits being changed to something else
        if is_user:
            status, message = handle_bridge_credit_changes(
                payment_method, club, session_entry, request.user, message
            )

    # TODO: Handle just paying with bridge credits or IOU, doesn't need to have changed type

    session_entry.is_paid = bool(form.cleaned_data["is_paid"])
    session_entry.payment_method = payment_method
    session_entry.save()

    # reset form and return
    form = UserSessionForm(club=club, session_entry=session_entry)

    return form, message


@user_is_club_director(include_session_entry=True)
def edit_session_entry_htmx(request, club, session, session_entry):
    """Edit a single session_entry on the session page

    We hide a lot of extra things in the form for this view

    The most significant changes involve Bridge Credits - if credits have been paid and we change to another
    payment method, then we need to make a refund.

    """

    # See if POSTed form or not
    if "save_session" in request.POST:
        form, message = _edit_session_entry_handle_post(request, club, session_entry)
    else:
        form = UserSessionForm(club=club, session_entry=session_entry)
        message = ""

    # Check if payment method used is still valid
    valid_payment_methods = [item[1] for item in form.fields["payment_method"].choices]

    # unset or in the list are both valid
    if session_entry.payment_method:
        payment_method_is_valid = (
            session_entry.payment_method.payment_method in valid_payment_methods
        )
    else:
        payment_method_is_valid = True

    response = render(
        request,
        "club_sessions/manage/edit_session_entry_htmx.html",
        {
            "club": club,
            "session": session,
            "session_entry": session_entry,
            "form": form,
            "message": message,
            "payment_method_is_valid": payment_method_is_valid,
        },
    )
    # See what the status is after this change
    recalculate_session_status(session)

    # We might have changed the status of the session, so reload totals
    # TODO: CAUSES LOOP
    response["HX-Trigger"] = "update_totals"

    return response


@user_is_club_director(include_session_entry=True)
def edit_session_entry_extras_htmx(request, club, session, session_entry, message=""):
    """Handle the extras part of the session entry edit screen - IOUs, misc payments etc"""

    # get this orgs miscellaneous payment types and payment methods
    misc_payment_types = MiscPayType.objects.filter(organisation=club)
    payment_methods = OrgPaymentMethod.objects.filter(active=True, organisation=club)

    player = get_user_or_unregistered_user_from_system_number(
        session_entry.system_number
    )

    # remove IOU and bridge credits unless a registered user
    if type(player) != User:
        payment_methods = payment_methods.exclude(
            payment_method__in=["IOU", "Bridge Credits"]
        )

    # Check for IOUs from any club
    user_pending_payments = UserPendingPayment.objects.filter(
        system_number=session_entry.system_number
    )

    # Get any existing misc payments for this session
    session_misc_payments = SessionMiscPayment.objects.filter(
        session_entry=session_entry
    )

    return render(
        request,
        "club_sessions/manage/edit_session_entry_extras_htmx.html",
        {
            "misc_payment_types": misc_payment_types,
            "payment_methods": payment_methods,
            "user_pending_payments": user_pending_payments,
            "session_entry": session_entry,
            "session": session,
            "player": player,
            "club": club,
            "session_misc_payments": session_misc_payments,
            "message": message,
        },
    )


@user_is_club_director(include_session_entry=True)
def change_payment_method_htmx(request, club, session, session_entry):
    """called when the payment method dropdown is changed on the session tab"""

    payment_method = get_object_or_404(
        OrgPaymentMethod, pk=request.POST.get("payment_method")
    )

    # Handle IOUs
    # TODO: HANDLE IOUs

    # Get the membership_type for this user and club, None means they are a guest
    member_membership_type = (
        MemberMembershipType.objects.filter(system_number=session_entry.system_number)
        .filter(membership_type__organisation=club)
        .first()
    )

    if member_membership_type:
        member_membership = member_membership_type.membership_type
    else:
        member_membership = None  # Guest

    fee = SessionTypePaymentMethodMembership.objects.filter(
        session_type_payment_method__session_type__organisation=club,
        session_type_payment_method__payment_method=payment_method,
        membership=member_membership,
    ).first()

    session_entry.payment_method = payment_method
    session_entry.fee = fee.fee
    session_entry.save()

    return HttpResponse(fee.fee)


@user_is_club_director(include_session_entry=True)
def change_paid_amount_status_htmx(request, club, session, session_entry):
    """Change the status of the amount paid for a user."""

    if session_entry.is_paid:
        session_entry.is_paid = False
        session_entry.save()
        if (
            session_entry.payment_method
            and session_entry.payment_method.payment_method == "IOU"
        ):
            handle_iou_changes_off(club, session_entry)
    else:
        session_entry.is_paid = True
        session_entry.save()
        if (
            session_entry.payment_method
            and session_entry.payment_method.payment_method == "IOU"
        ):
            handle_iou_changes_on(club, session_entry, request.user)

    # Check status now
    unpaid_count = (
        SessionEntry.objects.filter(session=session).filter(is_paid=False).count()
    )
    if unpaid_count > 1:
        return HttpResponse("")

    elif unpaid_count == 0:
        # No unpaid, mark as complete
        session.status = Session.SessionStatus.COMPLETE
        session.save()

    elif unpaid_count == 1:
        # one unpaid, so either un-ticked, or ticked second last. reset status
        session.status = Session.SessionStatus.CREDITS_PROCESSED
        session.save()

    # Include HX-Trigger in response, so we know to update the totals too
    response = HttpResponse("")
    response["HX-Trigger"] = "update_totals"
    return response


@user_is_club_director()
def session_totals_htmx(request, club, session):
    """Calculate totals for a session and return formatted header over htmx. Repeats a lot of what
    happens for loading the session tab in the first place."""

    # load static
    (
        session_entries,
        mixed_dict,
        session_fees,
        membership_type_dict,
    ) = load_session_entry_static(session, club)

    # augment the session_entries
    session_entries = augment_session_entries(
        session_entries, mixed_dict, membership_type_dict, session_fees, club
    )

    # do calculations
    session_entries = calculate_payment_method_and_balance(
        session_entries, session_fees, club
    )

    # calculate totals
    totals = session_totals_calculations(
        session, session_entries, session_fees, membership_type_dict
    )

    # Progress
    if session.status == Session.SessionStatus.DATA_LOADED:
        progress_colour = "danger"
        progress_percent = 20
    elif session.status == Session.SessionStatus.CREDITS_PROCESSED:
        progress_colour = "warning"
        progress_percent = 60
    elif session.status == Session.SessionStatus.COMPLETE:
        progress_colour = "success"
        progress_percent = 100

    # Get bridge credits for this org
    bridge_credits = bridge_credits_for_club(club)

    # See if anyone is paying with bridge credits
    paying_with_bridge_credits = any(
        session_entry.payment_method == bridge_credits
        for session_entry in session_entries
    )

    return render(
        request,
        "club_sessions/manage/totals_htmx.html",
        {
            "totals": totals,
            "session": session,
            "club": club,
            "progress_colour": progress_colour,
            "progress_percent": progress_percent,
            "paying_with_bridge_credits": paying_with_bridge_credits,
        },
    )


@user_is_club_director(include_session_entry=True)
def add_misc_payment_htmx(request, club, session, session_entry):
    """Adds a miscellaneous payment for a user in a session"""

    # load data from form
    misc_description = request.POST.get("misc_description")
    amount = float(request.POST.get("amount"))
    payment_method = get_object_or_404(
        OrgPaymentMethod, pk=request.POST.get("payment_method")
    )

    # validate
    if amount <= 0:
        return edit_session_entry_extras_htmx(
            request, message="Amount must be greater than zero"
        )

    # load member
    member = get_user_or_unregistered_user_from_system_number(
        session_entry.system_number
    )
    if not member:
        return edit_session_entry_extras_htmx(request, message="Error loading member")

    # Add misc payment
    session_misc_payment = SessionMiscPayment(
        session_entry=session_entry,
        description=misc_description,
        payment_method=payment_method,
        amount=amount,
    )
    session_misc_payment.save()

    message = f"{misc_description} added"

    # If payments have been made for this session_entry and it was bridge credits, then try to
    # process this now
    bridge_credits = bridge_credits_for_club(club)

    if session_misc_payment.payment_method == bridge_credits and session_entry.is_paid:
        if payment_api_batch(
            member=member,
            description=f"{session} - {session_misc_payment.description}",
            amount=amount,
            organisation=club,
            payment_type="Club Payment",
            session=session,
        ):
            session_misc_payment.payment_made = True
            session_misc_payment.save()
            message += " and payment made."

        else:
            # Failed payment. Cancel it.
            session_misc_payment.delete()
            message = "Payment failed. Try another payment method."

    # See if status has changed
    recalculate_session_status(session)

    response = edit_session_entry_extras_htmx(request, message=message)
    response["HX-Trigger"] = "update_totals"
    return response


@user_is_club_director()
def process_bridge_credits_htmx(request, club, session):
    """handle bridge credits for the session - called from a big button"""

    failures = None

    # Get bridge credits for this org
    bridge_credits = bridge_credits_for_club(club)

    if not bridge_credits:
        return tab_session_htmx(
            request,
            message="Bridge Credits are not set up for this organisation. Add through Settings if you wish to use Bridge Credits",
        )

    # Get any extras
    extras = get_extras_as_total_for_session_entries(session)

    # For each player go through and work out what they owe
    session_entries = SessionEntry.objects.filter(
        session=session, is_paid=False, payment_method=bridge_credits
    ).exclude(system_number__in=ALL_SYSTEM_ACCOUNTS)

    # Go back if no bridge credits being paid
    if not session_entries:
        session.status = Session.SessionStatus.CREDITS_PROCESSED
        session.save()
        message = f"No {BRIDGE_CREDITS} to process. Moving to Off-System Payments."

    else:
        success, failures = process_bridge_credits(
            session_entries, session, club, bridge_credits, extras
        )
        message = (
            f"{BRIDGE_CREDITS} processed. Success: {success}. Failure {len(failures)}."
        )

    # Include HX-Trigger in response so we know to update the totals too
    response = tab_session_htmx(
        request, message=message, bridge_credit_failures=failures
    )
    response["HX-Trigger"] = "update_totals"
    return response


@user_is_club_director(include_session_entry=True)
def toggle_paid_misc_session_payment_htmx(request, club, session, session_entry):
    """mark a misc session payment as paid or unpaid"""

    # Get data
    session_misc_payment = get_object_or_404(
        SessionMiscPayment, pk=request.POST.get("session_misc_payment_id")
    )

    # validate
    if session_misc_payment.session_entry != session_entry:
        return edit_session_entry_extras_htmx(
            request, message="Misc payment not for this session"
        )

    bridge_credits = bridge_credits_for_club(club)
    iou = iou_for_club(club)
    user = get_user_or_unregistered_user_from_system_number(
        session_misc_payment.session_entry.system_number
    )

    # Check user type and action - shouldn't ever happen
    if type(user) != User and session_misc_payment.payment_method in [
        bridge_credits,
        iou,
    ]:
        return edit_session_entry_extras_htmx(
            request,
            message=f"Not a registered user. Cannot pay with {session_misc_payment.payment_method}.",
        )

    if session_misc_payment.payment_made:
        # Was paid, now its not

        # handle bridge credits
        if session_misc_payment.payment_method == bridge_credits:
            refund_bridge_credit_for_extra(
                session_misc_payment, club, user, request.user
            )
            message = f"{user} refunded {GLOBAL_CURRENCY_SYMBOL}{session_misc_payment.amount:.2f}"

        # handle IOUs
        elif session_misc_payment.payment_method == iou:
            handle_iou_changes_off(club, session_entry)
            message = "IOU deleted"

        # Simple - just toggle paid status
        else:
            message = "Miscellaneous payment marked as unpaid"

        session_misc_payment.payment_made = False
        session_misc_payment.save()

    else:
        # Wasn't paid, now it is (probably - bridge credit payment or IOU could fail)
        # handle bridge credits
        if session_misc_payment.payment_method == bridge_credits:
            if pay_bridge_credit_for_extra(session_misc_payment, session, club, user):
                session_misc_payment.payment_made = True
                session_misc_payment.save()
                message = "Payment successful"
            else:
                message = f"{BRIDGE_CREDITS} payment failed for {user.full_name}"

        # handle IOUs
        elif session_misc_payment.payment_method == iou:
            handle_iou_changes_on(club, session_entry, request.user)
            session_misc_payment.payment_made = True
            session_misc_payment.save()
            message = "IOU set up and player notified"

        # Simple - just toggle paid status
        else:
            session_misc_payment.payment_made = True
            session_misc_payment.save()
            message = "Miscellaneous payment marked as paid"

    # See what the status is after this change
    recalculate_session_status(session)

    response = edit_session_entry_extras_htmx(request, message=message)
    response["HX-Trigger"] = "update_totals"
    return response


@user_is_club_director(include_session_entry=True)
def delete_misc_session_payment_htmx(request, club, session, session_entry):
    """Delete a misc session payment"""

    # Get data
    session_misc_payment = get_object_or_404(
        SessionMiscPayment, pk=request.POST.get("session_misc_payment_id")
    )

    # validate
    if session_misc_payment.session_entry != session_entry:
        return edit_session_entry_extras_htmx(
            request, message="Misc payment not for this session"
        )

    # handle already paid
    if session_misc_payment.payment_made:
        player = get_user_or_unregistered_user_from_system_number(
            session_entry.system_number
        )
        refund_bridge_credit_for_extra(session_misc_payment, club, player, request.user)
        session_misc_payment.delete()
        return edit_session_entry_extras_htmx(
            request, message="Refund issued and payment deleted"
        )

    # delete
    session_misc_payment.delete()
    return edit_session_entry_extras_htmx(
        request, message="Miscellaneous payment deleted"
    )


@user_is_club_director()
def add_table_htmx(request, club, session):
    """Add a table to a session"""

    add_table(session)

    return tab_session_htmx(request, message="Table added")


@user_is_club_director()
def process_off_system_payments_htmx(request, club, session):
    """mark all off system payments as paid - called from a big button. Only possible once bridge credits
    have been processed."""

    # TODO: What about IOUs - should they be processed first too?

    # Get bridge credits and ious for this org
    bridge_credits = bridge_credits_for_club(club)
    ious = iou_for_club(club)

    # Session entries
    SessionEntry.objects.filter(session=session).exclude(
        payment_method__in=[bridge_credits, ious]
    ).update(is_paid=True)

    # mark misc payments for this session as paid
    SessionMiscPayment.objects.filter(session_entry__session=session,).exclude(
        payment_method__in=[bridge_credits, ious]
    ).update(payment_made=True)

    # Mark session status as complete
    session.status = Session.SessionStatus.COMPLETE
    session.save()

    # Include HX-Trigger in response so we know to update the totals too
    response = tab_session_htmx(request, message="Off System payments made")
    response["HX-Trigger"] = "update_totals"
    return response


@user_is_club_director(include_session_entry=True)
def top_up_member_htmx(request, club, session, session_entry):
    """Called from the detail view to top up a member balance. Member pays Club and club tops up the member balance
    from their own funds.

    We use a function within organisations-finance to do the payment

    """
    if "save" not in request.POST:

        # Payment methods are anything except Bridge Credits and IOUs
        payment_methods = OrgPaymentMethod.objects.filter(
            active=True, organisation=club
        ).exclude(payment_method__in=["Bridge Credits", "IOU"])

        return render(
            request,
            "club_sessions/manage/top_up_member_balance_htmx.html",
            {
                "club": club,
                "session": session,
                "session_entry": session_entry,
                "payment_methods": payment_methods,
            },
        )

    # Get data from request
    amount = float(request.POST.get("amount"))
    payment_method = get_object_or_404(
        OrgPaymentMethod, pk=request.POST.get("payment_method")
    )

    member = get_object_or_404(User, system_number=session_entry.system_number)
    description = f"Top up of {GLOBAL_CURRENCY_SYMBOL}{amount:,.2f}"

    # Process form
    status, message = pay_member_from_organisation(
        request, club, amount, description, member
    )

    if status:
        # Successful, so add session extras
        SessionMiscPayment(
            session_entry=session_entry,
            description=description,
            payment_method=payment_method,
            amount=amount,
        ).save()

    # return whole edit page
    return edit_session_entry_htmx(request)
