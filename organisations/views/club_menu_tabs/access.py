from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from accounts.models import User
from organisations.decorators import check_club_menu_access
from organisations.models import Organisation, ORGS_RBAC_GROUPS_AND_ROLES
from organisations.views.club_menu_tabs.utils import (
    _menu_rbac_has_access,
    _menu_rbac_advanced_is_admin,
)
from rbac.core import (
    rbac_get_group_by_name,
    rbac_add_user_to_group,
    rbac_get_admin_group_by_name,
    rbac_add_user_to_admin_group,
    rbac_get_users_in_group,
    rbac_remove_user_from_group,
    rbac_remove_admin_user_from_group,
    rbac_get_admin_users_in_group,
)
from rbac.models import RBACUserGroup, RBACAdminUserGroup
from rbac.views import rbac_forbidden


@check_club_menu_access()
def basic_add_user_htmx(request, club):
    """Add a user to club rbac basic group. Returns HTMX"""

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

    return access_basic(request, club)


@check_club_menu_access()
def advanced_add_user_htmx(request, club):
    """Add a user to club rbac advanced group. Returns HTMX"""

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


@check_club_menu_access()
def basic_delete_user_htmx(request, club):
    """Remove a user from club rbac basic group. Returns HTMX"""

    user = get_object_or_404(User, pk=request.POST.get("user_id"))

    group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.basic")

    # Check for last user
    if rbac_get_users_in_group(group).count() == 1:
        return access_basic(request, club, "Cannot remove last administrator")

    rbac_remove_user_from_group(user, group)

    # Also remove admin
    admin_group = rbac_get_admin_group_by_name(
        f"{club.rbac_admin_name_qualifier}.admin"
    )
    rbac_remove_admin_user_from_group(user, admin_group)

    return access_basic(request, club)


@check_club_menu_access()
def advanced_delete_user_htmx(request, club):
    """Remove a user from club rbac advanced group. Returns HTMX"""

    # Check if this use is an admin (in RBAC admin group or has higher access)
    if not _menu_rbac_advanced_is_admin(club, request.user):
        return HttpResponse("Access denied")

    user = get_object_or_404(User, pk=request.POST.get("user_id"))
    group_name_item = request.POST.get("group_name_item")

    group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.{group_name_item}")
    rbac_remove_user_from_group(user, group)

    return access_advanced(request, club)


@check_club_menu_access()
def advanced_delete_admin_htmx(request, club):
    """Remove an admin from club rbac advanced group. Returns HTMX"""

    # Check if this use is an admin (in RBAC admin group or has higher access)
    if not _menu_rbac_advanced_is_admin(club, request.user):
        return HttpResponse("Access denied")

    user = get_object_or_404(User, pk=request.POST.get("user_id"))

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


@check_club_menu_access()
def advanced_add_admin_htmx(request, club):
    """Add an admin to club rbac advanced group. Returns HTMX"""

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


def access_basic(request, club, message=None):  # sourcery skip: list-comprehension
    """Do the work for the Access tab on the club menu for basic RBAC."""

    group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.basic")

    # Get users
    users = rbac_get_users_in_group(group)

    for user in users:
        user.hx_post = reverse("organisations:club_admin_access_basic_delete_user_htmx")
        user.hx_vars = f"club_id:{club.id},user_id:{user.id}"

    # Get roles
    roles = []
    for rule in ORGS_RBAC_GROUPS_AND_ROLES:
        roles.append(f"{ORGS_RBAC_GROUPS_AND_ROLES[rule]['description']} for {club}")

    return render(
        request,
        "organisations/club_menu/access/basic.html",
        {
            "club": club,
            "setup": "basic",
            "users": users,
            "roles": roles,
            "message": message,
        },
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
                "organisations:club_admin_access_advanced_delete_user_htmx"
            )
            user.hx_vars = (
                f"club_id:{club.id},user_id:{user.id},group_name_item:'{rule}'"
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
        "organisations/club_menu/access/advanced.html",
        {
            "club": club,
            "user_is_admin": user_is_admin,
            "disable_buttons": disable_buttons,
            "user_roles": user_roles,
            "admin_list": admin_list,
            "errors": errors,
        },
    )
