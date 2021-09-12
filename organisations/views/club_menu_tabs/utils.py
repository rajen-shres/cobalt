from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.models import UnregisteredUser
from accounts.views import invite_to_join
from cobalt.settings import COBALT_HOSTNAME
from organisations.decorators import check_club_menu_access
from organisations.models import MemberMembershipType, Organisation, MemberClubEmail
from organisations.views.club_menu_tabs.members import list_htmx
from organisations.views.general import get_rbac_model_for_state
from payments.models import MemberTransaction
from rbac.core import (
    rbac_user_has_role,
    rbac_get_admin_group_by_name,
    rbac_get_admin_users_in_group,
)
from rbac.views import rbac_forbidden


def _menu_rbac_has_access(club, user):
    """Check if this user has access to this club

    This can be from having rbac rights to this organisation
    or... having state access to the organisation
    or... being a global admin

    Args:
        club(Organisation) - organisation to check
        user(User) - user access to check

    Returns:
        Boolean - True or False for access
        Role (str) - Club role needed if access is denied

    """

    # Check club access
    club_role = f"orgs.org.{club.id}.edit"
    if rbac_user_has_role(user, club_role):
        return True, None

    # Check state access
    rbac_model_for_state = get_rbac_model_for_state(club.state)
    state_role = "orgs.state.%s.edit" % rbac_model_for_state
    if rbac_user_has_role(user, state_role):
        return True, None

    # Check global role
    if rbac_user_has_role(user, "orgs.admin.edit"):
        return True, None

    return False, club_role


def _user_is_uber_admin(club, user):
    """Check if this user has higher level access - state or global"""

    # check if in State group
    rbac_model_for_state = get_rbac_model_for_state(club.state)
    state_role = "orgs.state.%s.edit" % rbac_model_for_state
    if rbac_user_has_role(user, state_role):
        return True

    # Check for global role
    elif rbac_user_has_role(user, "orgs.admin.edit"):
        return True

    return False


def _menu_rbac_advanced_is_admin(club, user):
    """Check if the user is an RBAC admin for this club when using advanced RBAC set up"""

    admin_group = rbac_get_admin_group_by_name(
        f"{club.rbac_admin_name_qualifier}.admin"
    )
    admins = rbac_get_admin_users_in_group(admin_group)

    # Check if in admin group
    if user in admins:
        return True

    # Check for higher level access
    return _user_is_uber_admin(club, user)


def _member_count(club, reference_date=None):
    """Get member count for club with optional ref date"""

    if not reference_date:
        reference_date = timezone.now()

    return (
        MemberMembershipType.objects.filter(membership_type__organisation=club)
        .filter(start_date__lte=reference_date)
        .filter(Q(end_date__gte=reference_date) | Q(end_date=None))
        .count()
    )


def _tab_is_okay(request):
    """Common initial tasks for tabs:
    - get club
    - check RBAC access
    - check this is a post

     Args:
        request: standard request object

    Returns:
        status: Boolean. True - ok to continue, False - not okay
        error_page: HTTPResponse to return if status is False
        club - Organisation - club to use if status is True

    """
    if request.method != "POST":
        return False, HttpResponse("Error"), None

    # Get club
    club_id = request.POST.get("club_id")
    club = get_object_or_404(Organisation, pk=club_id)

    # Check security
    allowed, role = _menu_rbac_has_access(club, request.user)
    if not allowed:
        return False, rbac_forbidden(request, role), None

    return True, None, club


def get_members_balance(club: Organisation):
    """Get the total balance for members of this club"""

    member_list = MemberMembershipType.objects.filter(
        membership_type__organisation=club
    ).values("system_number")

    member_balances = (
        MemberTransaction.objects.filter(member__system_number__in=member_list)
        .filter(balance__gte=0)
        .order_by("member", "-created_date", "balance")
        .distinct("member")
        .values_list("balance")
    )

    total_balance = 0.0

    for item in member_balances:
        total_balance += float(item[0])

    return total_balance


@check_club_menu_access()
def invite_user_to_join_htmx(request, club):
    """Invite an unregistered user to sign up"""

    un_reg_id = request.POST.get("un_reg_id")
    un_reg = get_object_or_404(UnregisteredUser, pk=un_reg_id)

    club_email = MemberClubEmail.objects.filter(
        system_number=un_reg.system_number, organisation=club
    ).first()
    if club_email:
        email = club_email.email
    elif un_reg.email:
        email = un_reg.email
    else:
        return list_htmx(
            request, f"No email address found for {un_reg.full_name}. Invite not sent."
        )

    # Check for non-prod environments
    if COBALT_HOSTNAME not in ["myabf.com.au", "www.myabf.com.au"]:
        print(f"NOT sending to {email}. Substituted for dev email address")
        email = "m@rkguthrie.com"

    invite_to_join(
        un_reg=un_reg,
        email=email,
        requested_by_user=request.user,
        requested_by_org=club,
    )

    return list_htmx(request, f"Invite sent to {un_reg.full_name}")
