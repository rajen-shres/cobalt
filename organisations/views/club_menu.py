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

from club_sessions.models import Session
from events.models import Congress, CongressMaster
from organisations.decorators import check_club_menu_access
from organisations.forms import ResultsFileForm
from organisations.models import (
    Organisation,
)
from organisations.views.admin import (
    rbac_get_basic_and_advanced,
)
from organisations.views.club_menu_tabs.access import access_basic, access_advanced
from organisations.views.club_menu_tabs.utils import (
    _menu_rbac_has_access,
    _user_is_uber_admin,
    _member_count,
    get_members_balance,
)
from payments.payments_views.core import get_balance_and_recent_trans_org
from rbac.core import (
    rbac_user_has_role,
)
from rbac.models import RBACUserGroup, RBACGroupRole
from rbac.views import rbac_forbidden
from results.models import ResultsFile
from utils.utils import cobalt_paginator


@login_required()
def club_menu(request, club_id):
    """Main menu for club administrators to handle things.

    This uses a tabbed navigation panel with each tab providing distinct information.
    We use a different sub function to prepare the information for each tab to keep it clean.

    Args:
        club_id - organisation to view

    Returns:
        HttpResponse - page to edit organisation
    """

    club = get_object_or_404(Organisation, pk=club_id)

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

    return render(
        request,
        "organisations/club_menu/menu.html",
        {
            "club": club,
            "show_finance": show_finance,
            "show_congress": show_congress,
            "show_sessions": show_sessions,
            "other_clubs": other_clubs,
        },
    )


@check_club_menu_access()
def tab_access_htmx(request, club):
    """build the access tab in club menu"""

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
    member_count = _member_count(club)

    # Gets members active 28 days ago
    past = timezone.now() - datetime.timedelta(days=28)
    member_count_before = _member_count(club, past)

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

    return render(
        request,
        "organisations/club_menu/dashboard/dashboard_htmx.html",
        {
            "club": club,
            "member_count": member_count,
            "congress_count": congress_count,
            "staff_count": staff_count,
            "diff_28_days": diff_28_days,
        },
    )


@check_club_menu_access()
def tab_congress_htmx(request, club):
    """build the congress tab in club menu"""

    congress_masters = CongressMaster.objects.filter(org=club)

    return render(
        request,
        "organisations/club_menu/congress/congress_htmx.html",
        {"club": club, "congress_masters": congress_masters},
    )


@check_club_menu_access()
def tab_sessions_htmx(request, club):
    """build the sessions tab in club menu"""

    sessions = Session.objects.filter(session_type__organisation=club).order_by(
        "-session_date", "-pk"
    )

    things = cobalt_paginator(request, sessions, 3)

    hx_post = reverse("organisations:club_menu_tab_sessions_htmx")
    hx_vars = f"club_id:{club.id}"

    return render(
        request,
        "organisations/club_menu/sessions/sessions_htmx.html",
        {"club": club, "things": things, "hx_post": hx_post, "hx_vars": hx_vars},
    )


@check_club_menu_access()
def tab_finance_htmx(request, club):
    """build the finance tab in club menu"""

    balance, recent_trans = get_balance_and_recent_trans_org(club)

    members_balance = get_members_balance(club)

    return render(
        request,
        "organisations/club_menu/finance/finance_htmx.html",
        {
            "club": club,
            "balance": balance,
            "recent_trans": recent_trans,
            "members_balance": members_balance,
        },
    )


@check_club_menu_access()
def tab_forums_htmx(request, club):
    """build the forums tab in club menu"""

    return render(
        request, "organisations/club_menu/forums/forums_htmx.html", {"club": club}
    )


@check_club_menu_access()
def tab_results_htmx(request, club):
    """build the results tab in club menu"""

    recent_results = ResultsFile.objects.filter(organisation=club).order_by(
        "-created_at"
    )
    form = ResultsFileForm()

    return render(
        request,
        "organisations/club_menu/results/results_htmx.html",
        {"club": club, "recent_results": recent_results, "form": form},
    )
