"""
Map

The entry point is club_menu() which loads the page menu.html
Menu.html uses HTMX to load the tab pages e.g. tab_dashboard_htmx()

"""
import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from cobalt.settings import GLOBAL_MPSERVER
from events.models import Congress
from organisations.forms import OrgForm, MembershipTypeForm
from organisations.models import (
    ORGS_RBAC_GROUPS_AND_ROLES,
    Organisation,
    MembershipType,
    MemberMembershipType,
)
from organisations.views.admin import (
    rbac_get_basic_and_advanced,
    get_secretary_from_org_form,
)
from organisations.views.general import (
    get_rbac_model_for_state,
    get_club_data_from_masterpoints_centre,
    compare_form_with_mpc,
)
from payments.core import get_balance_and_recent_trans_org
from rbac.core import (
    rbac_get_group_by_name,
    rbac_get_users_in_group,
    rbac_user_has_role,
    rbac_add_user_to_group,
    rbac_remove_user_from_group,
    rbac_get_admin_group_by_name,
    rbac_remove_admin_user_from_group,
    rbac_get_admin_users_in_group,
    rbac_add_user_to_admin_group,
)
from rbac.models import RBACAdminUserGroup, RBACUserGroup, RBACGroupRole

from rbac.views import rbac_forbidden
from utils.views import masterpoint_query


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


def _menu_rbac_advanced_is_admin(club, user):
    """Check if the user is an RBAC admin for this club when using advanced RBAC set up"""

    admin_group = rbac_get_admin_group_by_name(
        f"{club.rbac_admin_name_qualifier}.admin"
    )
    admins = rbac_get_admin_users_in_group(admin_group)

    # Check if in admin group
    if user in admins:
        return True

    # check if in State group
    rbac_model_for_state = get_rbac_model_for_state(club.state)
    state_role = "orgs.state.%s.edit" % rbac_model_for_state
    if rbac_user_has_role(user, state_role):
        return True

    # Finally check for global role
    elif rbac_user_has_role(user, "orgs.admin.edit"):
        return True

    return False


def access_basic(request, club):  # sourcery skip: list-comprehension
    """Do the work for the Access tab on the club menu for basic RBAC."""

    group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.basic")

    # Get users
    users = rbac_get_users_in_group(group)

    for user in users:
        user.hx_post = reverse(
            "organisations:club_admin_access_basic_delete_user_htmx",
            kwargs={"club_id": club.id, "user_id": user.id},
        )

    # Get roles
    roles = []
    for rule in ORGS_RBAC_GROUPS_AND_ROLES:
        roles.append(f"{ORGS_RBAC_GROUPS_AND_ROLES[rule]['description']} {club}")

    return render(
        request,
        "organisations/club_menu/access_basic.html",
        {"club": club, "setup": "basic", "users": users, "roles": roles},
    )


def access_basic_div(request, club):  # sourcery skip: list-comprehension
    """Do the work for the Access tab on the club menu for basic RBAC."""

    group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.basic")

    # Get users
    users = rbac_get_users_in_group(group)

    for user in users:
        user.hx_post = reverse(
            "organisations:club_admin_access_basic_delete_user_htmx",
            kwargs={"club_id": club.id, "user_id": user.id},
        )

    # Get roles
    roles = []
    for rule in ORGS_RBAC_GROUPS_AND_ROLES:
        roles.append(f"{ORGS_RBAC_GROUPS_AND_ROLES[rule]['description']} {club}")

    return render(
        request,
        "organisations/club_menu/access_basic_div_htmx.html",
        {"club": club, "setup": "basic", "users": users, "roles": roles},
    )


def access_advanced(request, club, errors={}):
    """Do the work for the Access tab on the club menu for advanced RBAC."""

    # We have multiple groups to handle so we get a dictionary for users with the role as the key
    user_roles = {}
    admin_list = []

    for rule in ORGS_RBAC_GROUPS_AND_ROLES:

        # get group
        group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.{rule}")

        # Get users
        users = rbac_get_users_in_group(group)
        user_list = []
        for user in users:

            # link for HTMX hx_post to go to
            user.hx_post = reverse(
                "organisations:club_admin_access_advanced_delete_user_htmx",
                kwargs={
                    "club_id": club.id,
                    "user_id": user.id,
                    "group_name_item": rule,
                },
            )
            # unique id for this user and group
            user.delete_id = f"{rule}-{user.id}"

            user_list.append(user)

        desc = f"{ORGS_RBAC_GROUPS_AND_ROLES[rule]['description']}"

        user_roles[rule] = [desc, user_list]

        # Get admins
        admin_group = rbac_get_admin_group_by_name(
            f"{club.rbac_admin_name_qualifier}.admin"
        )
        admins = rbac_get_admin_users_in_group(admin_group)
        admin_list = []
        for admin in admins:
            admin.hx_post = reverse(
                "organisations:access_advanced_delete_admin_htmx",
                kwargs={
                    "club_id": club.id,
                    "user_id": admin.id,
                },
            )
            admin_list.append(admin)

    # Check if this use is an admin (in RBAC admin group or has higher access)
    user_is_admin = _menu_rbac_advanced_is_admin(club, request.user)

    # disable buttons (still show them) if user not admin
    disable_buttons = "" if user_is_admin else "disabled"

    return render(
        request,
        "organisations/club_menu/access_advanced.html",
        {
            "club": club,
            "user_is_admin": user_is_admin,
            "disable_buttons": disable_buttons,
            "user_roles": user_roles,
            "admin_list": admin_list,
            "errors": errors,
        },
    )


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

    # Check if we show the finance tab
    show_finance = rbac_user_has_role(request.user, f"orgs.org.{club.id}.edit")

    # Check if we show the congress tab
    show_congress = rbac_user_has_role(request.user, f"events.org.{club.id}.edit")

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
            "other_clubs": other_clubs,
        },
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


@login_required()
def tab_access_htmx(request):
    """build the access tab in club menu"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    # Access tab - we have basic or advanced which are very different so use two functions for this
    rbac_basic, rbac_advanced = rbac_get_basic_and_advanced(club)

    if rbac_basic:
        return access_basic(request, club)
    else:
        return access_advanced(request, club)


@login_required()
def tab_dashboard_htmx(request):
    """build the dashboard tab in club menu"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    # Get members active now
    now = timezone.now()
    member_count = (
        MemberMembershipType.objects.filter(membership_type__organisation=club)
        .filter(start_date__lte=now)
        .filter(Q(end_date__gte=now) | Q(end_date=None))
        .count()
    )

    # Gets members active 28 days ago
    past = timezone.now() - datetime.timedelta(days=28)
    member_count_before = (
        MemberMembershipType.objects.filter(membership_type__organisation=club)
        .filter(start_date__lte=past)
        .filter(Q(end_date__gte=past) | Q(end_date=None))
        .count()
    )

    diff_28_days = "{0:+d}".format(member_count - member_count_before)

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
        "organisations/club_menu/tab_dashboard_htmx.html",
        {
            "club": club,
            "member_count": member_count,
            "congress_count": congress_count,
            "staff_count": staff_count,
            "diff_28_days": diff_28_days,
        },
    )


@login_required()
def tab_comms_htmx(request):
    """build the comms tab in club menu"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    return render(
        request, "organisations/club_menu/tab_comms_htmx.html", {"club": club}
    )


@login_required()
def tab_congress_htmx(request):
    """build the congress tab in club menu"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    congresses = Congress.objects.filter(congress_master__org=club)

    return render(
        request,
        "organisations/club_menu/tab_congress_htmx.html",
        {"club": club, "congresses": congresses},
    )


@login_required()
def tab_finance_htmx(request):
    """build the finance tab in club menu"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    balance, recent_trans = get_balance_and_recent_trans_org(club)

    return render(
        request,
        "organisations/club_menu/tab_finance_htmx.html",
        {"club": club, "balance": balance, "recent_trans": recent_trans},
    )


@login_required()
def tab_members_htmx(request):
    """build the members tab in club menu"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    return render(
        request, "organisations/club_menu/tab_members_htmx.html", {"club": club}
    )


@login_required()
def tab_results_htmx(request):
    """build the results tab in club menu"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    return render(
        request, "organisations/club_menu/tab_results_htmx.html", {"club": club}
    )


@login_required()
def tab_settings_basic_htmx(request):
    """build the settings tab in club menu for editing basic details"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    message = ""

    # The form handles the RBAC checks

    # This is a POST even the first time so look for "save" to see if this really is a form submit
    real_post = "Save" in request.POST

    if not real_post:
        org_form = OrgForm(user=request.user, instance=club)
    else:
        org_form = OrgForm(request.POST, user=request.user, instance=club)

        if org_form.is_valid():
            org = org_form.save(commit=False)
            org.last_updated_by = request.user
            org.last_updated = timezone.localtime()
            org.save()

            # We can't use Django messages as they won't show until the whole page reloads
            message = "Organisation details updated"

    org_form = compare_form_with_mpc(org_form, club)

    # secretary is a bit fiddly so we pass as a separate thing
    secretary_id, secretary_name = get_secretary_from_org_form(org_form)

    # Check if this user is state or global admin - then they can change the State or org_id
    rbac_model_for_state = get_rbac_model_for_state(club.state)
    state_role = "orgs.state.%s.edit" % rbac_model_for_state
    if rbac_user_has_role(request.user, state_role) or rbac_user_has_role(
        request.user, "orgs.admin.edit"
    ):
        uber_admin = True
    else:
        uber_admin = False

    return render(
        request,
        "organisations/club_menu/tab_settings_basic_htmx.html",
        {
            "club": club,
            "org_form": org_form,
            "secretary_id": secretary_id,
            "secretary_name": secretary_name,
            "uber_admin": uber_admin,
            "message": message,
        },
    )


@login_required()
def tab_settings_basic_reload_htmx(request):
    """Reload data from MPC and return the settings basic tab"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    qry = f"{GLOBAL_MPSERVER}/clubDetails/{club.org_id}"
    data = masterpoint_query(qry)[0]

    club.name = data["ClubName"]
    club.state = data["VenueState"]
    club.postcode = data["VenuePostcode"]
    club.club_email = data["ClubEmail"]
    club.club_website = data["ClubWebsite"]
    club.address1 = data["VenueAddress1"]
    club.address2 = data["VenueAddress2"]
    club.suburb = data["VenueSuburb"]

    club.save()

    return tab_settings_basic_htmx(request)


@login_required()
def tab_settings_membership_htmx(request):
    """build the settings tab in club menu for editing membership types"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    membership_types = MembershipType.objects.filter(organisation=club)

    return render(
        request,
        "organisations/club_menu/tab_settings_membership_htmx.html",
        {
            "club": club,
            "membership_types": membership_types,
        },
    )


@login_required()
def club_menu_tab_settings_membership_edit_htmx(request):
    """Part of the settings tab for membership types to allow user to edit the membership type

    When a membership type is clicked on, this code is run and returns a form to edit the
    details.
    """

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    # Get membership type id
    membership_type_id = request.POST.get("membership_type_id")
    membership_type = get_object_or_404(MembershipType, pk=membership_type_id)

    form = MembershipTypeForm(instance=membership_type)

    return render(
        request,
        "organisations/club_menu/tab_settings_membership_edit_htmx.html",
        {
            "club": club,
            "membership_type": membership_type,
            "form": form,
        },
    )


@login_required()
def access_basic_add_user_htmx(request):
    """Add a user to club rbac basic group. Returns HTMX"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    # Get user
    user_id = request.POST.get("user_id")
    user = get_object_or_404(User, pk=user_id)

    # Get group
    group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.basic")

    # Add user to group
    rbac_add_user_to_group(user, group)

    # All users are admins
    admin_group = rbac_get_admin_group_by_name(
        f"{club.rbac_admin_name_qualifier}.admin"
    )
    rbac_add_user_to_admin_group(user, admin_group)

    return access_basic_div(request, club)


@login_required()
def access_advanced_add_user_htmx(request):
    """Add a user to club rbac advanced group. Returns HTMX"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    # Get user
    user_id = request.POST.get("user_id")
    user = get_object_or_404(User, pk=user_id)

    # Get group
    group_name_item = request.POST.get("group_name_item")

    group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.{group_name_item}")

    errors = {}
    if RBACUserGroup.objects.filter(group=group, member=user).exists():
        errors[group_name_item] = f"{user.first_name} is already in this group"
    else:
        rbac_add_user_to_group(user, group)

    return access_advanced(request, club, errors)


@login_required()
def access_basic_delete_user_htmx(request, club_id, user_id):
    """Remove a user from club rbac basic group. Returns HTMX"""

    club = get_object_or_404(Organisation, pk=club_id)
    user = get_object_or_404(User, pk=user_id)

    # Check security
    allowed, role = _menu_rbac_has_access(club, request.user)
    if not allowed:
        return rbac_forbidden(request, role)

    group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.basic")
    rbac_remove_user_from_group(user, group)

    # Also remove admin
    admin_group = rbac_get_admin_group_by_name(
        f"{club.rbac_admin_name_qualifier}.admin"
    )
    rbac_remove_admin_user_from_group(user, admin_group)

    return access_basic(request, club)


@login_required()
def access_advanced_delete_user_htmx(request, club_id, user_id, group_name_item):
    """Remove a user from club rbac advanced group. Returns HTMX"""

    club = get_object_or_404(Organisation, pk=club_id)
    user = get_object_or_404(User, pk=user_id)

    # Check if this use is an admin (in RBAC admin group or has higher access)
    if not _menu_rbac_advanced_is_admin(club, request.user):
        return HttpResponse("Access denied")

    group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.{group_name_item}")
    rbac_remove_user_from_group(user, group)

    return access_advanced(request, club)


@login_required()
def access_advanced_delete_admin_htmx(request, club_id, user_id):
    """Remove an admin from club rbac advanced group. Returns HTMX"""

    club = get_object_or_404(Organisation, pk=club_id)
    user = get_object_or_404(User, pk=user_id)

    # Check if this use is an admin (in RBAC admin group or has higher access)
    if not _menu_rbac_advanced_is_admin(club, request.user):
        return HttpResponse("Access denied")

    admin_group = rbac_get_admin_group_by_name(
        f"{club.rbac_admin_name_qualifier}.admin"
    )

    # Don't allow the last admin to be removed
    errors = {}

    if RBACAdminUserGroup.objects.filter(group=admin_group).count() > 1:
        rbac_remove_admin_user_from_group(user, admin_group)
    else:
        errors["admin"] = "Cannot delete the last admin user"

    return access_advanced(request, club, errors)


@login_required()
def access_advanced_add_admin_htmx(request):
    """Add an admin to club rbac advanced group. Returns HTMX"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    # Check if this use is an admin (in RBAC admin group or has higher access)
    if not _menu_rbac_advanced_is_admin(club, request.user):
        return HttpResponse("Access denied")

    # Get user
    user_id = request.POST.get("user_id")
    user = get_object_or_404(User, pk=user_id)

    admin_group = rbac_get_admin_group_by_name(
        f"{club.rbac_admin_name_qualifier}.admin"
    )

    rbac_add_user_to_admin_group(user, admin_group)

    return access_advanced(request, club)
