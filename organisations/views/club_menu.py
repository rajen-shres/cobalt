from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from accounts.models import User
from organisations.models import ORGS_RBAC_GROUPS_AND_ROLES, Organisation
from organisations.views.admin import _rbac_get_basic_and_advanced
from rbac.core import (
    rbac_get_group_by_name,
    rbac_get_users_in_group,
    rbac_remove_user_from_group,
    rbac_add_user_to_group,
)


def _club_menu_access_basic(club):  # sourcery skip: list-comprehension
    """Do the work for the Access tab on the club menu for basic RBAC."""

    group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.basic")
    users = rbac_get_users_in_group(group)

    for user in users:
        user.hx_post = reverse(
            "organisations:club_admin_access_basic_delete_user_htmx",
            kwargs={"club_id": club.id, "user_id": user.id},
        )

    roles = []
    for rule in ORGS_RBAC_GROUPS_AND_ROLES:
        roles.append(f"{ORGS_RBAC_GROUPS_AND_ROLES[rule]['description']} {club}")

    return users, roles


def _club_menu_access_advanced(club):
    """Do the work for the Access tab on the club menu for advanced RBAC."""

    return None


@login_required()
def club_menu(request, club_id):
    """Main menu for club administrators to handle things.

    This use a tabbed navigation panel with each tab providing distinct information.
    We use a different sub function to prepare the information for each tab to keep it clean.

    Args:
        club_id - organisation to view

    Returns:
        HttpResponse - page to edit organisation
    """

    # Check access
    # TODO: Work out what group to use
    # if not rbac_user_has_role(request.user, "orgs.org.%s.edit" % club_id):
    #     return rbac_forbidden(request, "orgs.org.%s.edit" % club_id)

    club = get_object_or_404(Organisation, pk=club_id)

    # Access tab - we have basic or advanced which are very different so use two functions for this
    rbac_basic, rbac_advanced = _rbac_get_basic_and_advanced(club)

    if rbac_basic:

        access_users, access_roles = _club_menu_access_basic(club)
    else:
        access = _club_menu_access_advanced(club)
        print(access)

    return render(
        request,
        "organisations/club_menu/menu.html",
        {
            "club": club,
            "access_basic": rbac_basic,
            "access_users": access_users,
            "access_roles": access_roles,
        },
    )


@login_required()
def club_admin_access_basic_delete_user_htmx(request, club_id, user_id):
    """Remove a user from club rbac basic group. Returns HTMX"""

    # TODO: RBAC
    club = get_object_or_404(Organisation, pk=club_id)
    user = get_object_or_404(User, pk=user_id)

    group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.basic")
    rbac_remove_user_from_group(user, group)

    access_users, access_roles = _club_menu_access_basic(club)

    return render(
        request,
        "organisations/club_menu/access_basic_div_htmx.html",
        {
            "club": club,
            "access_users": access_users,
            "access_roles": access_roles,
        },
    )


@login_required()
def club_admin_access_basic_add_user_htmx(request):
    """Add a user to club rbac basic group. Returns HTMX"""

    # TODO: RBAC
    if request.method != "POST":
        return HttpResponse("Error")

    # Get form parameters
    club_id = request.POST.get("club_id")
    user_id = request.POST.get("user_id")

    club = get_object_or_404(Organisation, pk=club_id)
    user = get_object_or_404(User, pk=user_id)

    group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.basic")
    rbac_add_user_to_group(user, group)

    access_users, access_roles = _club_menu_access_basic(club)

    return render(
        request,
        "organisations/club_menu/access_basic_div_htmx.html",
        {
            "club": club,
            "access_users": access_users,
            "access_roles": access_roles,
        },
    )
