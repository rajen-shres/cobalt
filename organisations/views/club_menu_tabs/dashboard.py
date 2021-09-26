from datetime import timedelta

from dateutil.relativedelta import relativedelta
from django.shortcuts import render
from django.utils import timezone

from accounts.models import User, UnregisteredUser
from organisations.decorators import check_club_menu_access
from organisations.models import MemberMembershipType
from rbac.models import RBACUserGroup


@check_club_menu_access()
def dashboard_members_htmx(request, club):
    """show basic member data"""

    club_members = (
        MemberMembershipType.objects.active()
        .filter(membership_type__organisation=club)
        .values_list("system_number")
    )
    myabf_members = User.objects.filter(system_number__in=club_members).count()
    visitors = 0
    un_regs = UnregisteredUser.objects.filter(system_number__in=club_members).count()

    return render(
        request,
        "organisations/club_menu/dashboard/members_chart_htmx.html",
        {
            "myabf_members": myabf_members,
            "un_regs": un_regs,
            "visitors": visitors,
            "has_members": club_members.exists(),
        },
    )


@check_club_menu_access()
def dashboard_member_changes_htmx(request, club):
    """show total member numbers by month"""

    now = timezone.now()
    data = []
    labels = []

    for month in range(-11, 1):
        ref_date = now + relativedelta(months=month)
        print(month, ref_date)
        club_members = (
            MemberMembershipType.objects.active(ref_date)
            .filter(membership_type__organisation=club)
            .values_list("system_number")
            .count()
        )

        data.append(club_members)
        labels.append(ref_date.strftime("%b"))

    return render(
        request,
        "organisations/club_menu/dashboard/members_changes_htmx.html",
        {"data": data, "labels": labels, "max_value": max(data)},
    )


@check_club_menu_access()
def dashboard_staff_htmx(request, club):
    """show basic member data"""

    staff_nos = (
        RBACUserGroup.objects.filter(group__rbacgrouprole__model_id=club.id)
        .filter(group__name_qualifier=club.rbac_name_qualifier)
        .values_list("member")
        .distinct()
    )

    staff = User.objects.filter(id__in=staff_nos)

    return render(
        request, "organisations/club_menu/dashboard/staff_htmx.html", {"staff": staff}
    )
