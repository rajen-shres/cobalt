"""
Map

The entry point is club_menu() which loads the page menu.html
Menu.html uses HTMX to load the tab pages e.g. tab_dashboard_htmx()

"""
import datetime

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserAdditionalInfo
from accounts.views.core import (
    get_user_or_unregistered_user_from_system_number,
)
from club_sessions.models import Session
from events.models import Congress, CongressMaster
from organisations.decorators import check_club_menu_access
from organisations.forms import ResultsEmailMessageForm
from organisations.models import (
    Organisation,
    OrgEmailTemplate,
    ClubLog,
)
from organisations.views.admin import (
    rbac_get_basic_and_advanced,
)
from organisations.views.club_menu_tabs.access import access_basic, access_advanced
from organisations.views.club_menu_tabs.utils import (
    _menu_rbac_has_access,
    _user_is_uber_admin,
    get_member_count,
    get_members_balance,
)
from payments.models import UserPendingPayment
from payments.views.core import org_balance
from rbac.core import (
    rbac_user_has_role,
)
from rbac.models import RBACUserGroup, RBACGroupRole
from rbac.views import rbac_forbidden
from results.models import ResultsFile
from utils.utils import cobalt_paginator


@login_required()
def club_menu(
    request, club_id, change_to_last_visited=False, show_tab="dashboard", click_id=None
):
    """Main menu for club administrators to handle things.

    This uses a tabbed navigation panel with each tab providing distinct information.
    We use a different sub function to prepare the information for each tab to keep it clean.

    Args:
        club_id - organisation to view
        show_tab - the name of the tab to be shown initially (for COB-766)
        click_id - the html id of a control on teh tab to be sent a click event on entry

    Returns:
        HttpResponse - page to edit organisation
    """

    # Get additional info to read and update
    user_additional_info, _ = UserAdditionalInfo.objects.get_or_create(
        user=request.user
    )

    # See if we should show the last visited club
    if change_to_last_visited and user_additional_info.last_club_visited:
        club = get_object_or_404(
            Organisation, pk=user_additional_info.last_club_visited
        )
    else:
        club = get_object_or_404(Organisation, pk=club_id)
        user_additional_info.last_club_visited = club_id
        user_additional_info.save()

    # Check if staff member for other clubs - get all from tree that are like "clubs.generated"
    other_club_ids = (
        RBACGroupRole.objects.filter(group__rbacusergroup__member=request.user)
        .filter(group__name_qualifier__contains="clubs.generated")
        .values("model_id")
        .distinct()
    )
    if len(other_club_ids) > 1:
        other_clubs = Organisation.objects.filter(pk__in=other_club_ids).exclude(
            pk=club.id
        )
    else:
        other_clubs = None

    # Check access
    allowed, role = _menu_rbac_has_access(club, request.user)
    if not allowed:
        return rbac_forbidden(request, role)

    # Reduce database calls
    uber_admin = _user_is_uber_admin(club, request.user)

    # Check if we show the finance tab
    show_finance = (
        uber_admin
        or rbac_user_has_role(request.user, f"payments.manage.{club.id}.view")
        or rbac_user_has_role(request.user, f"payments.manage.{club.id}.edit")
    )
    # Check if we show the congress tab
    show_congress = uber_admin or rbac_user_has_role(
        request.user, f"events.org.{club.id}.edit"
    )
    # Check if we show the sessions tab
    show_sessions = uber_admin or rbac_user_has_role(
        request.user, f"club_sessions.sessions.{club.id}.edit"
    )

    return render(
        request,
        "organisations/club_menu/menu.html",
        {
            "club": club,
            "show_finance": show_finance,
            "show_congress": show_congress,
            "show_sessions": show_sessions,
            "other_clubs": other_clubs,
            "show_tab": show_tab,
            "click_id": click_id,
        },
    )


@check_club_menu_access()
def tab_access_htmx(request, club):
    """build the access tab in club menu"""

    # JPG debug
    print("********** LOADING ACCESS TAB ****************")

    # Access tab - we have basic or advanced which are very different so use two functions for this
    rbac_basic, rbac_advanced = rbac_get_basic_and_advanced(club)

    if rbac_basic:
        return access_basic(request, club)
    elif rbac_advanced:
        return access_advanced(request, club)
    else:
        return HttpResponse(
            "<h3>This club has not been set up normally. Unable to manage access through the Club Menu.</h3>"
        )


@check_club_menu_access()
def tab_dashboard_htmx(request, club):
    """build the dashboard tab in club menu"""

    # Get members active now
    member_count = get_member_count(club)

    # Gets members active 28 days ago
    past = timezone.now() - datetime.timedelta(days=28)
    member_count_before = get_member_count(club, past)

    diff = member_count - member_count_before
    diff_28_days = "No change" if diff == 0 else f"{diff:+,}"
    congress_count = Congress.objects.filter(congress_master__org=club).count()
    staff_count = (
        RBACUserGroup.objects.filter(group__rbacgrouprole__model_id=club.id)
        .filter(group__name_qualifier=club.rbac_name_qualifier)
        .values_list("member")
        .distinct()
        .count()
    )

    # Get any outstanding set up required
    has_templates = OrgEmailTemplate.objects.all().exists()
    public_profile_edited = ClubLog.objects.filter(
        action="Updated public profile", organisation=club
    ).exists()
    has_members = member_count > 0

    warnings = (
        not has_templates
        or not club.bank_bsb
        or not club.bank_account
        or not public_profile_edited
        or not has_members
    )

    # See if this has just been set up
    try:
        is_initial = ClubLog.objects.latest("pk").action == "Initial defaults set up"
    except ClubLog.DoesNotExist:
        is_initial = False

    return render(
        request,
        "organisations/club_menu/dashboard/dashboard_htmx.html",
        {
            "club": club,
            "member_count": member_count,
            "congress_count": congress_count,
            "staff_count": staff_count,
            "diff_28_days": diff_28_days,
            "has_templates": has_templates,
            "public_profile_edited": public_profile_edited,
            "has_members": has_members,
            "is_initial": is_initial,
            "warnings": warnings,
        },
    )


@check_club_menu_access()
def tab_congress_htmx(request, club):
    """build the congress tab in club menu"""

    # JPG debug
    print("********** LOADING CONGRESS TAB ****************")

    congress_masters = CongressMaster.objects.filter(org=club)

    for congress_master in congress_masters:
        congress_master.has_congresses = bool(
            Congress.objects.filter(congress_master=congress_master).exists()
        )

    # Show button for draft congresses if there are any
    show_draft = (
        Congress.objects.filter(congress_master__org=club)
        .filter(status="Draft")
        .exists()
    )

    return render(
        request,
        "organisations/club_menu/congress/congress_htmx.html",
        {"club": club, "congress_masters": congress_masters, "show_draft": show_draft},
    )


@check_club_menu_access()
def tab_sessions_htmx(request, club, message=""):
    """build the sessions tab in club menu"""

    # JPG debug
    print("********** LOADING SESSION TAB ****************")

    sessions = (
        Session.objects.filter(session_type__organisation=club)
        .order_by("-session_date", "-pk")
        .select_related("session_type")
    )

    things = cobalt_paginator(request, sessions)

    hx_post = reverse("organisations:club_menu_tab_sessions_htmx")
    hx_vars = f"club_id:{club.id}"

    return render(
        request,
        "organisations/club_menu/sessions/sessions_htmx.html",
        {
            "club": club,
            "things": things,
            "hx_post": hx_post,
            "hx_vars": hx_vars,
            "message": message,
        },
    )


@login_required()
def tab_finance_statement(request, club_id):
    """Entry point for the new club finance statement, for COB-766"""

    return club_menu(request, club_id, show_tab="finance")


@login_required()
def tab_comms_edit_batch_ep(request, club_id, batch_id_id):
    """Entry point for editing an email batch under the comms tab

    Used when wanting to navigate from outside the club menu to the comms tab
    and editing a specific inflight batch"""

    return club_menu(
        request, club_id, show_tab="comms", click_id=f"id_{batch_id_id}_edit_button"
    )


@login_required()
def tab_entry_point(request, club_id, tab_name):
    """Entry point for showing a specified tab"""

    return club_menu(request, club_id, show_tab=tab_name)


@check_club_menu_access()
def tab_finance_htmx(request, club, message=""):
    """build the finance tab in club menu"""

    # Get balance and transactions
    balance = org_balance(club)

    # Get member balances
    members_balance = get_members_balance(club)

    # Get any outstanding debts
    user_pending_payments = UserPendingPayment.objects.filter(organisation=club)

    # augment data
    for user_pending_payment in user_pending_payments:
        user_pending_payment.player = get_user_or_unregistered_user_from_system_number(
            user_pending_payment.system_number
        )
        user_pending_payment.hx_delete = reverse(
            "organisations:club_menu_tab_finance_cancel_user_pending_debt_htmx"
        )
        user_pending_payment.hx_vars = (
            f"club_id:{club.id}, user_pending_payment_id:{user_pending_payment.id}"
        )

    return render(
        request,
        "organisations/club_menu/finance/finance_htmx.html",
        {
            "club": club,
            "balance": balance,
            "members_balance": members_balance,
            "user_pending_payments": user_pending_payments,
            "message": message,
        },
    )


@check_club_menu_access()
def tab_forums_htmx(request, club):
    """build the forums tab in club menu"""

    return render(
        request, "organisations/club_menu/forums/forums_htmx.html", {"club": club}
    )


@check_club_menu_access()
def tab_results_htmx(request, club, message=None):
    """build the results tab in club menu"""

    recent_results = ResultsFile.objects.filter(organisation=club).order_by(
        "-event_date"
    )

    things = cobalt_paginator(request, recent_results)

    hx_post = reverse("organisations:club_menu_tab_results_htmx")
    hx_vars = f"club_id:{club.id}"
    hx_delete = reverse("organisations:club_menu_tab_results_delete_results_file_htmx")

    for thing in things:
        thing.hx_vars = f"club_id:{club.id},results_file_id:{thing.id}"

    # Get results email form
    results_email_message_form = ResultsEmailMessageForm(instance=club)

    # See if a template exists for results
    results_template_exists = OrgEmailTemplate.objects.filter(
        organisation=club, template_name="Results"
    ).exists()

    return render(
        request,
        "organisations/club_menu/results/results_htmx.html",
        {
            "club": club,
            "things": things,
            "hx_post": hx_post,
            "hx_delete": hx_delete,
            "hx_vars": hx_vars,
            "message": message,
            "results_email_message_form": results_email_message_form,
            "results_template_exists": results_template_exists,
        },
    )
