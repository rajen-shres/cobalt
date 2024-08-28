"""
Club Administration Shared Views

Vies used by both members and contacts.
"""

# jpg debug
from django.template.loader import render_to_string

from datetime import datetime
from itertools import chain

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import (
    User,
    UnregisteredUser,
)
from club_sessions.models import SessionEntry
from cobalt.settings import (
    GLOBAL_ORG,
    GLOBAL_TITLE,
    COBALT_HOSTNAME,
    GLOBAL_CURRENCY_SYMBOL,
    BRIDGE_CREDITS,
)
from events.models import (
    EventEntryPlayer,
)
from events.views.core import (
    get_events,
    _get_event_start_date_from_sessions,
)
from notifications.views.core import (
    get_emails_sent_to_address,
)
from organisations.decorators import check_club_menu_access
from organisations.club_admin_core import (
    club_email_for_member,
    get_member_details,
    get_valid_activities,
    get_club_contact_list,
    get_club_member_list,
    get_club_member_list_email_match,
    get_club_contact_list_email_match,
    log_member_change,
)
from organisations.models import (
    ClubLog,
    ClubTag,
    MemberClubDetails,
    MemberClubTag,
    MemberMembershipType,
    MiscPayType,
)
from payments.models import MemberTransaction
from payments.views.payments_api import (
    payment_api_batch,
    payment_api_interactive,
)
from payments.views.core import (
    get_balance,
    org_balance,
    update_account,
    update_organisation,
)
from rbac.core import rbac_user_has_role
from utils.utils import (
    cobalt_paginator,
    cobalt_currency,
)


@check_club_menu_access(check_members=True)
def activity_tags_htmx(request, club):
    """Show the tags activity subview

    Called via hx-post with hx-vars club_id (dereferenced in the decorator) and system_number
    """

    system_number = request.POST.get("system_number")
    member_details = get_member_details(club, system_number)

    # Get member tags
    member_tags = MemberClubTag.objects.prefetch_related("club_tag").filter(
        club_tag__organisation=club, system_number=member_details.system_number
    )
    used_tags = member_tags.values("club_tag__tag_name")
    available_tags = ClubTag.objects.filter(organisation=club).exclude(
        tag_name__in=used_tags
    )

    return render(
        request,
        "organisations/club_admin/activity_tags_htmx.html",
        {
            "club": club,
            "member": member_details,
            "system_number": system_number,
            "permitted_activities": get_valid_activities(member_details),
            "member_tags": member_tags,
            "available_tags": available_tags,
        },
    )


@check_club_menu_access(check_members=True)
def activity_emails_htmx(request, club):
    """Show the emails activity subview

    Called via hx-post with hx-vars club_id (dereferenced in the decorator) and system_number
    """

    system_number = request.POST.get("system_number")
    member_details = get_member_details(club, system_number)

    email_address = club_email_for_member(club, system_number)

    if email_address:
        emails = get_emails_sent_to_address(email_address, club, request.user)
        if not emails:
            message = "No emails available"
    else:
        emails = None
        message = "No email address for this person"

    return render(
        request,
        "organisations/club_admin/activity_emails_htmx.html",
        {
            "club": club,
            "system_number": system_number,
            "permitted_activities": get_valid_activities(member_details),
            "emails": emails,
            "message": message,
        },
    )


@check_club_menu_access(check_members=True)
def activity_entries_htmx(request, club):
    """Show the entries activity subview

    Called via hx-post with hx-vars club_id (dereferenced in the decorator) and system_number
    """

    system_number = request.POST.get("system_number")
    member_details = get_member_details(club, system_number)
    user = get_object_or_404(User, system_number=system_number)

    events, _, more_events, total_events = get_events(user)
    past_events, more_past_events, total_past_events = _get_past_events(user)

    return render(
        request,
        "organisations/club_admin/activity_entries_htmx.html",
        {
            "club": club,
            "member_details": member_details,
            "system_number": member_details.system_number,
            "permitted_activities": get_valid_activities(member_details),
            "events": events,
            "more_events": more_events,
            "total_events": total_events,
            "past_events": past_events,
            "more_past_events": more_past_events,
            "total_past_events": total_past_events,
        },
    )


def _get_past_events(user):
    """Recent past event entries for a player"""

    # Load event_entry_players for this user
    event_entry_players, more_events, total_events = _get_past_event_entry_players(user)

    event_start_dates = _get_event_start_date_from_sessions(event_entry_players)

    # Augment data
    for event_entry_player in event_entry_players:
        # Set start date based upon sessions

        event_entry_player.calculated_start_date = event_start_dates[
            event_entry_player.event_entry.event
        ]

        if event_entry_player.calculated_start_date == timezone.localdate():
            event_entry_player.is_running = True

    return event_entry_players, more_events, total_events


def _get_past_event_entry_players(user):
    """sub of _get_past_events to handle the main things to do with event_entry_players"""

    # Main query
    event_entry_players_query = (
        EventEntryPlayer.objects.filter(
            player=user, event_entry__event__denormalised_end_date__lt=datetime.today()
        )
        .exclude(event_entry__entry_status="Cancelled")
        .order_by("-event_entry__event__denormalised_start_date")
        .select_related("event_entry__event")
    )

    # total number of events this user has coming up
    total_events = event_entry_players_query.count()

    # get last 6
    event_entry_players = event_entry_players_query[:6]

    # We get 6 but show 5. If we have 6 then show the more button
    more_events = len(event_entry_players) == 6

    # Drop the 6th if we have one
    event_entry_players = event_entry_players[:5]

    return event_entry_players, more_events, total_events


@check_club_menu_access(check_members=True)
def activity_sessions_htmx(request, club):
    """Show the session activity subview

    Called via hx-post with hx-vars club_id (dereferenced in the decorator) and system_number
    """

    system_number = request.POST.get("system_number")
    member_details = get_member_details(club, system_number)

    sessions = (
        SessionEntry.objects.filter(system_number=system_number)
        .order_by("-session__session_date")
        .select_related("session")
    )

    things = cobalt_paginator(request, sessions, 10)

    # Add hx_post for paginator controls
    hx_post = reverse("organisations:club_admin_activity_sessions_htmx")
    hx_vars = f"club_id:{club.id}, system_number:{member_details.system_number}"
    hx_target = "#id-activity-card"

    return render(
        request,
        "organisations/club_admin/activity_sessions_htmx.html",
        {
            "club": club,
            "member_details": member_details,
            "things": things,
            "hx_post": hx_post,
            "hx_vars": hx_vars,
            "hx_target": hx_target,
            "system_number": member_details.system_number,
            "permitted_activities": get_valid_activities(member_details),
        },
    )


@check_club_menu_access(check_members=True)
def activity_transactions_htmx(request, club):
    """Show the sessions activity subview

    Called via hx-post with hx-vars club_id (dereferenced in the decorator) and system_number
    """

    system_number = request.POST.get("system_number")

    # validate membership
    member_details = get_member_details(club, system_number)
    if not member_details:
        return HttpResponse("This person is not a club member")
    if member_details.user_type != f"{GLOBAL_TITLE} User":
        return HttpResponse(f"This person is not a registered {GLOBAL_TITLE} user")
    if member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_CONTACT:
        return HttpResponse("You can only access transaction details for club members")

    # get member - must be User to have transactions
    member = get_object_or_404(User, system_number=system_number)

    # Get payment stuff
    recent_payments, misc_payment_types = _get_misc_payment_vars(member, club)

    # Get users balance
    user_balance = get_balance(member)
    club_balance = org_balance(club)

    # See if this user has payments access
    user_has_payments_edit = rbac_user_has_role(
        request.user, f"club_sessions.sessions.{club.id}.edit"
    ) or rbac_user_has_role(request.user, f"payments.manage.{club.id}.edit")

    # See if user has payments view access
    if user_has_payments_edit:
        user_has_payments_view = True
    else:
        user_has_payments_view = rbac_user_has_role(
            request.user, f"payments.manage.{club.id}.view"
        )

    return render(
        request,
        "organisations/club_admin/activity_transactions_htmx.html",
        {
            "club": club,
            "member": member,
            "system_number": member_details.system_number,
            "permitted_activities": get_valid_activities(member_details),
            "recent_payments": recent_payments,
            "misc_payment_types": misc_payment_types,
            "user_balance": user_balance,
            "club_balance": club_balance,
            "user_has_payments_edit": user_has_payments_edit,
            "user_has_payments_view": user_has_payments_view,
        },
    )


def _get_misc_payment_vars(member, club):
    """get variables relating to this members misc payments for this club"""

    # Get recent misc payments
    recent_payments = MemberTransaction.objects.filter(
        member=member, organisation=club
    ).order_by("-created_date")[:10]

    # get this orgs miscellaneous payment types
    misc_payment_types = MiscPayType.objects.filter(organisation=club)

    return recent_payments, misc_payment_types


@check_club_menu_access(check_session_or_payments=True)
def add_misc_payment_htmx(request, club):
    """Adds a miscellaneous payment for a user. Could be the club charging them, or the club paying them"""

    # load data from form
    misc_description = request.POST.get("misc_description")
    member = get_object_or_404(User, pk=request.POST.get("member_id"))
    amount = float(request.POST.get("amount"))
    charge_or_pay = request.POST.get("charge_or_pay")

    member_details = get_member_details(club, member.system_number)

    charge_message = ""
    pay_message = ""

    if amount <= 0:
        if charge_or_pay == "charge":
            charge_message = "Amount must be greater than zero"
        else:
            pay_message = "Amount must be greater than zero"

    if charge_or_pay == "charge":
        charge_message = _add_misc_payment_charge(
            request, club, member, amount, misc_description
        )
    else:
        pay_message = _add_misc_payment_pay(
            request, club, member, amount, misc_description
        )

    # Get relevant data
    recent_payments, misc_payment_types = _get_misc_payment_vars(member, club)

    # Get balance
    user_balance = get_balance(member)
    club_balance = org_balance(club)

    # User has payments edit, no need to check again
    user_has_payments_edit = True

    # return part of edit_member screen
    return render(
        request,
        "organisations/club_admin/activity_transactions_htmx.html",
        {
            "club": club,
            "member": member,
            "system_number": member.system_number,
            "permitted_activities": get_valid_activities(member_details),
            "pay_message": pay_message,
            "charge_message": charge_message,
            "recent_payments": recent_payments,
            "misc_payment_types": misc_payment_types,
            "user_balance": user_balance,
            "club_balance": club_balance,
            "user_has_payments_edit": user_has_payments_edit,
        },
    )


def _add_misc_payment_charge(request, club, member, amount, misc_description):
    """handle club charging user"""

    if payment_api_batch(
        member=member,
        amount=amount,
        description=f"{misc_description}",
        organisation=club,
    ):
        misc_message = "Payment successful"
        ClubLog(
            organisation=club,
            actor=request.user,
            action=f"Made misc payment of {GLOBAL_CURRENCY_SYMBOL}{amount:,.2f} for '{misc_description}' - {member}",
        ).save()

    else:
        misc_message = f"Payment FAILED for {member.full_name}. Insufficient funds."

    return misc_message


def _add_misc_payment_pay(request, club, member, amount, misc_description):
    """Handle club paying a member"""

    if org_balance(club) < amount:
        return "Club has insufficient funds for this transaction."

    # make payments
    update_account(
        member=member,
        amount=amount,
        description=misc_description,
        organisation=club,
        payment_type="Miscellaneous",
    )
    update_organisation(
        member=member,
        amount=-amount,
        description=misc_description,
        organisation=club,
        payment_type="Miscellaneous",
    )

    # log it
    ClubLog(
        organisation=club,
        actor=request.user,
        action=f"{member} - {cobalt_currency(amount)} - {misc_description}",
    ).save()

    return "Payment successful"


@check_club_menu_access(check_members=True)
def activity_invitations_htmx(request, club):
    """Show the invitations activity subview

    Called via hx-post with hx-vars club_id (dereferenced in the decorator) and system_number
    """

    system_number = request.POST.get("system_number")
    member_details = get_member_details(club, system_number)

    un_reg = get_object_or_404(UnregisteredUser, system_number=system_number)

    return render(
        request,
        "organisations/club_admin/activity_invitations_htmx.html",
        {
            "club": club,
            "member_details": member_details,
            "system_number": member_details.system_number,
            "permitted_activities": get_valid_activities(member_details),
            "un_reg": un_reg,
        },
    )


@check_club_menu_access(check_members=True)
def activity_none_htmx(request, club):
    """Close the current recent activity view"""

    system_number = request.POST.get("system_number")
    member_details = get_member_details(club, system_number)

    return render(
        request,
        "organisations/club_admin/activity_none_htmx.html",
        {
            "club": club,
            "member_details": member_details,
            "system_number": member_details.system_number,
            "permitted_activities": get_valid_activities(member_details),
        },
    )


# -----------------------------------------------------------------------------------------
#  Member and Contact Search
# -----------------------------------------------------------------------------------------


@check_club_menu_access(check_members=True)
def search_tab_htmx(request, club):
    """Display a search page"""

    mode = request.POST.get("mode", "members")

    member_admin = rbac_user_has_role(request.user, f"orgs.members.{club.id}.edit")

    return render(
        request,
        "organisations/club_admin/search_tab_htmx.html",
        {
            "member_admin": member_admin,
            "club": club,
            "mode": mode,
            "full_membership_mgmt": club.full_club_admin,
        },
    )


@check_club_menu_access()
def search_tab_name_htmx(request, club):
    """Search function for searching for a member or contact by name"""

    mode = request.POST.get("mode", "members")
    first_name_search = request.POST.get("first_name_search")
    last_name_search = request.POST.get("last_name_search")

    # jpg debug
    print(f"search_tab_name_htmx {mode} '{first_name_search}' '{last_name_search}'' ")

    # if there is nothing to search for, don't search
    if not first_name_search and not last_name_search:
        return HttpResponse()

    if mode == "members":
        system_number_list = get_club_member_list(club)
    else:
        system_number_list = get_club_contact_list(club)

    # jpg debug
    # print(f"system numbers = {system_number_list}")

    # Users
    users = User.objects.filter(system_number__in=system_number_list)

    if first_name_search:
        users = users.filter(first_name__istartswith=first_name_search)

    if last_name_search:
        users = users.filter(last_name__istartswith=last_name_search)

    # Unregistered
    un_regs = UnregisteredUser.objects.filter(system_number__in=system_number_list)

    if first_name_search:
        un_regs = un_regs.filter(first_name__istartswith=first_name_search)

    if last_name_search:
        un_regs = un_regs.filter(last_name__istartswith=last_name_search)

    user_list = list(chain(users, un_regs))

    # jpg debug
    # print(f"user_list len={len(user_list)}")

    # debug_str= render_to_string(
    #     "organisations/club_admin/search_tab_results_htmx.html",
    #     {"user_list": user_list, "club": club, "mode": mode},
    # )
    # print(debug_str)

    return render(
        request,
        "organisations/club_admin/search_tab_results_htmx.html",
        {"user_list": user_list, "club": club, "mode": mode},
    )


@check_club_menu_access()
def search_tab_email_htmx(request, club):
    """Search function for searching for a member or contact by email"""

    mode = request.POST.get("mode", "members")
    email_search = request.POST.get("email_search")

    # if there is nothing to search for, don't search
    if not email_search:
        return HttpResponse()

    if mode == "members":
        system_number_list = get_club_member_list_email_match(club, email_search)
    else:
        system_number_list = get_club_contact_list_email_match(club, email_search)

    users = User.objects.filter(system_number__in=system_number_list)

    un_regs = UnregisteredUser.objects.filter(system_number__in=system_number_list)

    user_list = list(chain(users, un_regs))

    return render(
        request,
        "organisations/club_admin/search_tab_results_htmx.html",
        {"user_list": user_list, "club": club, "mode": mode},
    )


@login_required()
def user_initiated_payment(request, mmt_id):
    """User wants to pay a membership fee by Bridge Credits."""

    def refresh_with_warning(message):

        messages.warning(
            request,
            message,
            extra_tags="cobalt-message-warning",
        )

        return redirect("accounts:user_profile")

    mmt = (
        MemberMembershipType.objects.filter(pk=mmt_id)
        .select_related("membership_type", "membership_type__organisation")
        .last()
    )

    if not mmt:
        return HttpResponse("Error: record no longer exists")

    if mmt.system_number != request.user.system_number:
        return refresh_with_warning("Error: not your fee to pay")

    if (
        mmt.fee == 0
        or mmt.is_paid
        or mmt.membership_state
        not in [
            MemberMembershipType.MEMBERSHIP_STATE_CURRENT,
            MemberMembershipType.MEMBERSHIP_STATE_DUE,
            MemberMembershipType.MEMBERSHIP_STATE_FUTURE,
        ]
    ):
        return refresh_with_warning("Error: fee no longer payable")

    # ok to proceed with payment

    return payment_api_interactive(
        request,
        request.user,
        f"Membership Fee {mmt.membership_type.organisation.name}",
        mmt.fee,
        organisation=mmt.membership_type.organisation,
        payment_type="Club Membership",
        route_code="CAU",
        route_payload=f"{mmt_id}",
        next_url=reverse(
            "accounts:user_profile",
        ),
    )


@login_required()
def user_initiated_payment_success_htmx(request, mmt_id):
    """Payment has been successful ?"""

    return render(
        request,
        "accounts/profile/profile_payment_response_htmx.html",
        {
            "mmt_id": mmt_id,
            "message": "Payment made",
            "disable_payment_button": True,
        },
    )


def user_initiated_fee_payment_callback(status, payload):
    """Callback from payments API, payment has been made
    Payload is the MemberMembershipType id"""

    if status == "Success":

        mmt_id = int(payload)
        mmt = (
            MemberMembershipType.objects.filter(pk=mmt_id)
            .select_related("membership_type", "membership_type__organisation")
            .last()
        )

        # mark membership as paid
        mmt.is_paid = True
        mmt.paid_until_date = mmt.end_date
        mmt.paid_date = timezone.now().date()
        mmt.auto_pay_date = None
        if mmt.membership_state == MemberMembershipType.MEMBERSHIP_STATE_DUE:
            mmt.membership_state = MemberMembershipType.MEMBERSHIP_STATE_CURRENT

            # update the membership details record
            member_details = MemberClubDetails.objects.filter(
                system_number=mmt.system_number,
                club=mmt.membership_type.organisation,
            ).last()
            member_details.membership_status = mmt.membership_state
            member_details.save()

        mmt.save()

        user = User.objects.get(system_number=mmt.system_number)

        log_member_change(
            mmt.membership_type.organisation,
            mmt.system_number,
            user,
            f"Member paid fee by {BRIDGE_CREDITS}",
        )
