from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from accounts.models import User, UnregisteredUser
from accounts.views.core import get_user_or_unregistered_user_from_system_number
from club_sessions.forms import SessionForm, UserSessionForm
from club_sessions.models import (
    Session,
    SessionEntry,
    SessionMiscPayment,
    SessionTypePaymentMethodMembership,
)
from club_sessions.views.core import (
    handle_change_additional_session_fee,
    handle_change_additional_session_fee_reason,
    handle_change_secondary_payment_method,
    load_session_entry_static,
    augment_session_entries,
    get_allowed_payment_methods,
    get_summary_table_data,
    get_table_view_data,
    edit_session_entry_handle_ious,
    edit_session_entry_handle_bridge_credits,
    recalculate_session_status,
    handle_iou_changes_off,
    handle_iou_changes_on,
    calculate_payment_method_and_balance,
    session_totals_calculations,
    bridge_credits_for_club,
    get_extras_as_total_for_session_entries,
    process_bridge_credits,
    iou_for_club,
    refund_bridge_credit_for_extra,
    pay_bridge_credit_for_extra,
    add_table,
    change_user_on_session_entry,
    delete_table,
    edit_session_entry_handle_other,
    get_session_fee_for_player,
    handle_iou_changes_for_misc_off,
    handle_iou_changes_for_misc_on,
    back_out_top_up,
    SITOUT,
    PLAYING_DIRECTOR,
)
from club_sessions.views.decorators import user_is_club_director
from cobalt.settings import ALL_SYSTEM_ACCOUNTS, BRIDGE_CREDITS, GLOBAL_CURRENCY_SYMBOL
from organisations.models import Organisation, MiscPayType, MemberMembershipType
from organisations.views.club_menu_tabs.finance import (
    pay_member_from_organisation,
    top_up_member_from_organisation,
)
from payments.models import OrgPaymentMethod, UserPendingPayment
from payments.views.core import get_balance
from payments.views.payments_api import payment_api_batch
from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden


@login_required()
def manage_session(request, session_id):
    """Main page to manage a club session after it has been created.

    Not much happens in this function, mostly it just renders the page.

    The different tabs look after themselves: tab_settings_htmx, tab_session_htmx live here
    and the reports run from their own file.

    """

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
        "club_sessions/shared/settings_htmx.html",
        {
            "session_form": session_form,
            "club": club,
            "session": session,
            "message": message,
            "director_name": director_name,
        },
    )

    # Reload sessions tab if we change anything, also send the description and date in case they have changed
    if "save_settings" in request.POST:
        response[
            "HX-Trigger"
        ] = f"""{{"reload_sessions": "true", "new_title": "{session.description}", "new_date": "{session.session_date:%-d %b %Y}" }}"""

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
        "summary": "club_sessions/manage/views/session_summary_view_htmx.html",
        "detail": "club_sessions/manage/views/session_detail_view_htmx.html",
        "table": "club_sessions/manage/views/session_table_view_htmx.html",
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
        table_list, table_status, delete_table_available = get_table_view_data(
            session, session_entries
        )
    else:
        table_list = {}
        table_status = {}
        delete_table_available = {}

    # See if we have any extras
    has_extras = SessionMiscPayment.objects.filter(
        session_entry__session=session
    ).exists()

    return render(
        request,
        template,
        {
            "club": club,
            "session": session,
            "session_entries": session_entries,
            "table_list": table_list,
            "table_status": table_status,
            "delete_table_available": delete_table_available,
            "payment_methods": payment_methods,
            "payment_summary": payment_summary,
            "message": message,
            "bridge_credit_failures": bridge_credit_failures,
            "has_extras": has_extras,
        },
    )


def _edit_session_entry_handle_post(request, club, session, session_entry):
    """Sub for edit_session_entry_htmx to handle the form being posted"""

    message = "Data saved. "

    form = UserSessionForm(request.POST, club=club, session_entry=session_entry)
    if not form.is_valid():
        print(form.errors)
        return form, "There were errors on the form"

    # The "after" data is on the form, the "before" data is on the session_entry
    # It makes the code easier to follow if we are explicit about which is which

    old_payment_method = session_entry.payment_method
    if "payment_method" in form.changed_data:
        new_payment_method = OrgPaymentMethod.objects.get(
            pk=form.cleaned_data["payment_method"]
        )
    else:
        new_payment_method = old_payment_method

    old_fee = session_entry.fee
    new_fee = form.cleaned_data["fee"]
    old_is_paid = session_entry.is_paid
    new_is_paid = form.cleaned_data["is_paid"]

    # get user type
    is_user = request.POST.get("is_user")

    # The payment method dictates most of the logic
    handled_flag = False

    # Handle bridge credits being impacted
    if "Bridge Credits" in [
        new_payment_method.payment_method,
        old_payment_method.payment_method,
    ]:
        message, session_entry = edit_session_entry_handle_bridge_credits(
            club,
            session,
            session_entry,
            request.user,
            is_user,
            old_payment_method,
            new_payment_method,
            old_fee,
            new_fee,
            old_is_paid,
            new_is_paid,
        )
        handled_flag = True

    # Handle IOUs (Could be bridge credits and IOUs involved)
    if "IOU" in [new_payment_method.payment_method, old_payment_method.payment_method]:
        message, session_entry = edit_session_entry_handle_ious(
            club,
            session_entry,
            request.user,
            old_payment_method,
            new_payment_method,
            old_fee,
            new_fee,
            old_is_paid,
            new_is_paid,
            message,
        )
        handled_flag = True

    # Handle any other cases
    if not handled_flag:
        message, session_entry = edit_session_entry_handle_other(
            club,
            session_entry,
            request.user,
            is_user,
            old_payment_method,
            new_payment_method,
            old_fee,
            new_fee,
            old_is_paid,
            new_is_paid,
        )

    # reset form and return
    form = UserSessionForm(club=club, session_entry=session_entry)

    return form, message


@user_is_club_director(include_session_entry=True)
def edit_session_entry_htmx(request, club, session, session_entry, message=""):
    """Edit a single session_entry on the session page

    We hide a lot of extra things in the form for this view

    The most significant changes involve Bridge Credits - if credits have been paid and we change to another
    payment method, then we need to make a refund.

    """

    # See if POSTed form or not
    if "save_session" in request.POST:
        form, message = _edit_session_entry_handle_post(
            request, club, session, session_entry
        )
    else:
        form = UserSessionForm(club=club, session_entry=session_entry)

    # Check if payment method used is still valid
    valid_payment_methods = [item[1] for item in form.fields["payment_method"].choices]

    # unset or in the list are both valid
    if session_entry.payment_method:
        payment_method_is_valid = (
            session_entry.payment_method.payment_method in valid_payment_methods
        )
    else:
        payment_method_is_valid = True

    # See what the status is after this change
    recalculate_session_status(session)

    response = render(
        request,
        "club_sessions/manage/edit_entry/edit_session_entry_htmx.html",
        {
            "club": club,
            "session": session,
            "session_entry": session_entry,
            "form": form,
            "message": message,
            "payment_method_is_valid": payment_method_is_valid,
        },
    )

    # We might have changed the status of the session, so reload totals
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

    # let template know if this is a registered user
    if type(player) == User:
        player.is_user = True

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
        "club_sessions/manage/edit_entry/edit_session_entry_extras_htmx.html",
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

    extras = (
        SessionMiscPayment.objects.filter(session_entry=session_entry)
        .values("session_entry")
        .annotate(extras=Sum("amount"))
    )

    total = fee.fee

    if extras:
        total += extras[0]["extras"]

    # Use htmx Out of Band option to also update the total

    return HttpResponse(
        f"""<div>{fee.fee}</div>
                            <div id="id_session_entry_total_{session_entry.id }" hx-swap-oob="true"> {total:.2f} </div>
                            <div id="detail_message" hx-swap-oob="true">Session Updated</div>
                            """
    )


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
        SessionEntry.objects.filter(session=session)
        .filter(is_paid=False)
        .exclude(system_number__in=[SITOUT, PLAYING_DIRECTOR])
        .count()
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
    response["HX-Trigger"] = '{"update_totals": 1, "refresh_balance": 1}'
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
    extras = get_extras_as_total_for_session_entries(
        session, payment_method_string=BRIDGE_CREDITS, unpaid_only=True
    )

    # For each player go through and work out what they owe
    session_entries = SessionEntry.objects.filter(
        session=session, is_paid=False, payment_method=bridge_credits
    ).exclude(system_number__in=ALL_SYSTEM_ACCOUNTS)

    # Process payments if we have any to make
    if session_entries or extras:
        success, failures = process_bridge_credits(
            session_entries, session, club, bridge_credits, extras
        )
        message = (
            f"{BRIDGE_CREDITS} processed. Success: {success}. Failure {len(failures)}."
        )

    else:
        session.status = Session.SessionStatus.CREDITS_PROCESSED
        session.save()
        message = f"No {BRIDGE_CREDITS} to process. Moving to Off-System Payments."

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
            handle_iou_changes_for_misc_off(club, session_entry, session_misc_payment)
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
            handle_iou_changes_for_misc_on(
                club, session_entry, session_misc_payment, request.user
            )
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
    response["HX-Trigger"] = '{"update_totals": 1, "refresh_balance": 1}'

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

    # Get player
    player = get_user_or_unregistered_user_from_system_number(
        session_entry.system_number
    )

    # Was it a top up? If so reverse it but we can just delete the misc payment - can't be bridge credits
    if session_misc_payment.payment_type == SessionMiscPayment.TypeOfPayment.TOP_UP:
        back_out_top_up(session_misc_payment, club, player, request.user)
        session_misc_payment.delete()
        return edit_session_entry_extras_htmx(
            request, message="Top Up reversed, and misc payment removed"
        )

    # handle already paid
    if (
        session_misc_payment.payment_made
        and session_misc_payment.payment_method.payment_method == "Bridge Credits"
    ):
        refund_bridge_credit_for_extra(session_misc_payment, club, player, request.user)
        session_misc_payment.delete()
        return edit_session_entry_extras_htmx(
            request, message="Refund issued and payment deleted"
        )

    # simple delete
    session_misc_payment.delete()
    response = edit_session_entry_extras_htmx(
        request, message="Miscellaneous payment deleted"
    )

    response["HX-Trigger"] = '{"update_totals": 1, "refresh_balance": 1}'
    return response


@user_is_club_director()
def add_table_htmx(request, club, session):
    """Add a table to a session"""

    add_table(session)

    return tab_session_htmx(request, message="Table added")


@user_is_club_director()
def delete_table_htmx(request, club, session):
    """Add a table to a session"""

    table_number = request.POST.get("table_number")

    if delete_table(session, table_number):
        message = "Table deleted"
    else:
        message = "Unable to delete table"

    return tab_session_htmx(request, message=message)


@user_is_club_director()
def process_off_system_payments_htmx(request, club, session):
    """mark all off system payments as paid - called from a big button. Only possible once bridge credits
    have been processed."""

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

    # Handle IOUs
    session_entry_ious = SessionEntry.objects.filter(
        session=session, payment_method=ious, is_paid=False
    )
    for session_entry_iou in session_entry_ious:
        handle_iou_changes_on(club, session_entry_iou, request.user)

    # handle IOUs for extras
    extras_ious = SessionMiscPayment.objects.filter(
        session_entry__session=session, payment_method=ious, payment_made=False
    )
    for extra_iou in extras_ious:
        handle_iou_changes_for_misc_on(
            club, extra_iou.session_entry, extra_iou, request.user
        )

    # Mark session status as complete
    recalculate_session_status(session)

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

        player = get_object_or_404(User, system_number=session_entry.system_number)

        return render(
            request,
            "club_sessions/manage/edit_entry/top_up_member_balance_htmx.html",
            {
                "club": club,
                "session": session,
                "session_entry": session_entry,
                "payment_methods": payment_methods,
                "player": player,
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
    status, message = top_up_member_from_organisation(
        request, club, amount, description, member
    )

    if status:
        # Successful, so add session extras
        SessionMiscPayment(
            session_entry=session_entry,
            description=description,
            payment_method=payment_method,
            amount=amount,
            payment_type=SessionMiscPayment.TypeOfPayment.TOP_UP,
        ).save()

    # return whole edit page
    return edit_session_entry_htmx(request)


@user_is_club_director(include_session_entry=True)
def change_player_htmx(request, club, session, session_entry):
    """Change a player to another. We could get any of the following:

    source and system number for a User or UnregisteredUser
    sitout - change to a sitout
    playing_director - change to a playing director
    non_abf_visitor - someone who isn't registered with the ABF, also get the first and last name

    """

    source = request.POST.get("source")
    system_number = request.POST.get("system_number")
    sitout = request.POST.get("sitout")
    playing_director = request.POST.get("playing_director")
    non_abf_visitor = request.POST.get("non_abf_visitor")
    member_last_name_search = request.POST.get("member_last_name_search")
    member_first_name_search = request.POST.get("member_first_name_search")

    message = change_user_on_session_entry(
        club,
        session,
        session_entry,
        source,
        system_number,
        sitout,
        playing_director,
        non_abf_visitor,
        member_last_name_search,
        member_first_name_search,
        request.user,
    )

    # return whole edit page
    return tab_session_htmx(request, message=message)


@user_is_club_director(include_session_entry=True)
def get_fee_for_payment_method_htmx(request, club, session, session_entry):
    """Called by the edit panel to get what the fee should be when we change the payment method"""

    payment_method = get_object_or_404(
        OrgPaymentMethod, pk=request.POST.get("payment_method_id")
    )
    session_entry.payment_method = payment_method

    return HttpResponse(get_session_fee_for_player(session_entry, club))


@user_is_club_director()
def predict_bridge_credits_failures_htmx(request, club, session):
    """Used in the totals part if we are about to pay for bridge credits to show expected failures"""

    # Get unpaid extras as a dictionary keyed on session_entry.pk
    extras = get_extras_as_total_for_session_entries(
        session, unpaid_only=True, payment_method_string=BRIDGE_CREDITS
    )

    # Get session entries with unpaid bridge credits
    bridge_credit_payments = SessionEntry.objects.filter(
        session=session, payment_method__payment_method=BRIDGE_CREDITS, is_paid=False
    )

    # Get users who don't have auto top up
    bridge_credit_system_number_list = bridge_credit_payments.values("system_number")
    users = User.objects.filter(
        system_number__in=bridge_credit_system_number_list
    ).exclude(stripe_auto_confirmed="Yes")

    # Turn into a dict and also get balance
    users_dict = {}
    for user in users:
        user.balance = get_balance(user)
        users_dict[user.system_number] = user

    # Go through and build a list of warnings
    warnings = []
    for bridge_credit_payment in bridge_credit_payments:
        due = float(bridge_credit_payment.fee) + extras.get(bridge_credit_payment.id, 0)
        dict_value = users_dict.get(bridge_credit_payment.system_number)
        if dict_value:
            balance = dict_value.balance
            if due > balance:
                warnings.append(
                    {
                        "user": users_dict[bridge_credit_payment.system_number],
                        "due": due,
                        "balance": balance,
                    }
                )

    return render(
        request,
        "club_sessions/manage/predict_bridge_credits_failures_htmx.html",
        {"warnings": warnings, "session": session},
    )
