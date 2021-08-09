from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone

from accounts.models import User
from organisations.forms import OrgForm
from organisations.models import Organisation, ORGS_RBAC_GROUPS_AND_ROLES
from organisations.views import general
from rbac.core import (
    rbac_user_has_role,
    rbac_get_group_by_name,
    rbac_create_group,
    rbac_add_user_to_group,
    rbac_add_role_to_group,
    rbac_create_admin_group,
    rbac_add_user_to_admin_group,
    rbac_admin_add_tree_to_group,
    rbac_get_users_in_group_by_name,
    rbac_delete_group_by_name,
    rbac_get_users_in_group,
    rbac_delete_group,
)
from rbac.views import rbac_forbidden


@login_required()
def admin_add_club(request):
    """Add a club to the system. For State or ABF Administrators

    NOTE: For now the club must be defined in the Masterpoints Centre already

    """
    # TODO: Get rid of higher up edit org function and replace with this

    # The form handles the RBAC checks
    form = OrgForm(request.POST or None, user=request.user)

    if request.method == "POST" and form.is_valid():
        org = form.save(commit=False)
        org.last_updated_by = request.user
        org.last_updated = timezone.localtime()
        org.type = "Club"
        org.save()
        messages.success(
            request, f"{org.name} created", extra_tags="cobalt-message-success"
        )
        return redirect("organisations:admin_club_rbac", club_id=org.id)

    # secretary is a bit fiddly so we pass as a separate thing
    secretary_id = form["secretary"].value()
    secretary_name = User.objects.filter(pk=secretary_id).first()

    return render(
        request,
        "organisations/admin_add_club.html",
        {"form": form, "secretary_id": secretary_id, "secretary_name": secretary_name},
    )


@login_required()
def admin_list_clubs(request):
    """List Clubs in the system. For State or ABF Administrators"""

    clubs = Organisation.objects.filter(type="Club").order_by("state", "name")

    return render(request, "organisations/admin_list_clubs.html", {"clubs": clubs})


def _rbac_user_has_admin(club, user):
    """Check if this user has access to do rbac admin for this club"""

    # Get model id for this state
    rbac_model_for_state = general.get_rbac_model_for_state(club.state)

    # Check access
    role = "orgs.state.%s.edit" % rbac_model_for_state
    if not (
        rbac_user_has_role(user, role) or rbac_user_has_role(user, "orgs.admin.edit")
    ):
        return False, role

    return True, None


def rbac_get_basic_and_advanced(club):
    """Get the setup for this club"""

    # Basic is e.g. rbac.orgs.clubs.generated.nsw.34.basic (we can't use the club name as it might change, use pk)
    rbac_basic = rbac_get_group_by_name(
        "rbac.orgs.clubs.generated.%s.%s.basic" % (club.state.lower(), club.id)
    )

    # Advanced has a few groups e.g. rbac.orgs.clubs.generated.nsw.34.conveners
    # Assume conveners will always work
    rbac_advanced = rbac_get_group_by_name(
        "rbac.orgs.clubs.generated.%s.%s.conveners" % (club.state.lower(), club.id)
    )

    return bool(rbac_basic), bool(rbac_advanced)


@login_required()
def admin_club_rbac(request, club_id):
    """Manage RBAC basic set up for a Club

    This doesn't control who gets access - clubs can do that themselves, this controls whether it is basic
    or advanced RBAC configuration. It is the RBAC structure, not the content.

    """

    # Get club
    club = get_object_or_404(Organisation, pk=club_id)

    has_access, role = _rbac_user_has_admin(club, request.user)
    if not has_access:
        return rbac_forbidden(request, role)

    # Check rbac setup
    rbac_basic, rbac_advanced = rbac_get_basic_and_advanced(club)

    error = ""
    new_setup = False

    if rbac_advanced and rbac_basic:
        error = "Error: This club is set up with both simple and advanced RBAC. Contact Support."

    if not rbac_advanced and not rbac_basic:
        error = "RBAC not set up yet."
        new_setup = True

    return render(
        request,
        "organisations/admin_club_rbac.html",
        {
            "club": club,
            "new_setup": new_setup,
            "rbac_basic": rbac_basic,
            "rbac_advanced": rbac_advanced,
            "error": error,
        },
    )


def _admin_club_rbac_add_basic_sub(club):
    """low level steps to add rbac basic for club"""

    # Create group
    group = rbac_create_group(
        name_qualifier=club.rbac_name_qualifier,
        name_item="basic",
        description=f"Basic security group for org {club.id} ({club.name})",
    )
    # Add user
    rbac_add_user_to_group(club.secretary, group)

    # Add roles
    for rule in ORGS_RBAC_GROUPS_AND_ROLES:
        rbac_add_role_to_group(
            group=group,
            app=ORGS_RBAC_GROUPS_AND_ROLES[rule]["app"],
            model=ORGS_RBAC_GROUPS_AND_ROLES[rule]["model"],
            action=ORGS_RBAC_GROUPS_AND_ROLES[rule]["action"],
            rule_type="Allow",
            model_id=club.id,
        )

    # Also add orgs.org as this is the easiest way to check if a user should have access
    rbac_add_role_to_group(
        group=group,
        app="orgs",
        model="org",
        action="view",
        rule_type="Allow",
        model_id=club.id,
    )

    # Add admin - no need to add roles, the tree is enough for user admin
    admin_group = rbac_create_admin_group(
        name_qualifier=club.rbac_admin_name_qualifier,
        name_item="admin",
        description=f"Admin people for {club.id} ({club.name})",
    )
    rbac_add_user_to_admin_group(club.secretary, admin_group)

    # Don't give user tree access to this branch or they can create new groups
    # TODO: Test this
    rbac_admin_add_tree_to_group(admin_group, club.rbac_admin_name_qualifier + ".basic")


@login_required()
def admin_club_rbac_add_basic(request, club_id):
    """Manage RBAC basic set up for a Club

    This doesn't control who gets access - clubs can do that themselves, this controls whether it is basic
    or advanced RBAC configuration. It is the RBAC structure, not the content.

    """

    # Get club
    club = get_object_or_404(Organisation, pk=club_id)

    has_access, role = _rbac_user_has_admin(club, request.user)
    if not has_access:
        return rbac_forbidden(request, role)

    # Check rbac setup
    rbac_basic, rbac_advanced = rbac_get_basic_and_advanced(club)

    # Double check before creating
    if rbac_advanced or rbac_basic:
        messages.error(
            request,
            "This club is already set up with RBAC.",
            extra_tags="cobalt-message-error",
        )
    else:  # create it

        _admin_club_rbac_add_basic_sub(club)

        messages.success(
            request,
            f"{club.name} set up with Basic RBAC",
            extra_tags="cobalt-message-success",
        )

    return redirect("organisations:admin_club_rbac", club_id=club.id)


def _admin_club_rbac_add_advanced_sub(club):
    """low level steps to add rbac advanced for club"""

    # Create groups

    # Create admin group - no need to add roles, the tree is enough for user admin
    admin_group = rbac_create_admin_group(
        name_qualifier=club.rbac_admin_name_qualifier,
        name_item="admin",
        description=f"Admin people for {club.id} ({club.name})",
    )
    rbac_add_user_to_admin_group(club.secretary, admin_group)

    # Add roles - multiple groups with a single role each
    for rule in ORGS_RBAC_GROUPS_AND_ROLES:
        group = rbac_create_group(
            name_qualifier=club.rbac_name_qualifier,
            name_item=rule,
            description=f"{ORGS_RBAC_GROUPS_AND_ROLES[rule]['description']} for {club.id} ({club.name})",
        )
        # Add user
        rbac_add_user_to_group(club.secretary, group)

        rbac_add_role_to_group(
            group=group,
            app=ORGS_RBAC_GROUPS_AND_ROLES[rule]["app"],
            model=ORGS_RBAC_GROUPS_AND_ROLES[rule]["model"],
            action=ORGS_RBAC_GROUPS_AND_ROLES[rule]["action"],
            rule_type="Allow",
            model_id=club.id,
        )

        # Also add orgs.org as this is the easiest way to check if a user should have access
        rbac_add_role_to_group(
            group=group,
            app="orgs",
            model="org",
            action="view",
            rule_type="Allow",
            model_id=club.id,
        )

        # Add admin tree
        rbac_admin_add_tree_to_group(admin_group, club.rbac_name_qualifier + f".{rule}")


@login_required()
def admin_club_rbac_add_advanced(request, club_id):
    """Manage RBAC advanced set up for a Club

    This doesn't control who gets access - clubs can do that themselves, this controls whether it is basic
    or advanced RBAC configuration. It is the RBAC structure, not the content.

    """

    # Get club
    club = get_object_or_404(Organisation, pk=club_id)

    has_access, role = _rbac_user_has_admin(club, request.user)
    if not has_access:
        return rbac_forbidden(request, role)

    # Check rbac setup
    rbac_basic, rbac_advanced = rbac_get_basic_and_advanced(club)

    # Double check before creating
    if rbac_advanced or rbac_basic:
        messages.error(
            request,
            "This club is already set up with RBAC.",
            extra_tags="cobalt-message-error",
        )
    else:  # create it

        _admin_club_rbac_add_advanced_sub(club)

        messages.success(
            request,
            f"{club.name} set up with Advanced RBAC",
            extra_tags="cobalt-message-success",
        )

    return redirect("organisations:admin_club_rbac", club_id=club.id)


@login_required()
def admin_club_rbac_convert_basic_to_advanced(request, club_id):
    """Change rbac setup for a club basic -> advanced"""

    # Get club
    club = get_object_or_404(Organisation, pk=club_id)

    has_access, role = _rbac_user_has_admin(club, request.user)
    if not has_access:
        return rbac_forbidden(request, role)

    # Check rbac setup
    rbac_basic, rbac_advanced = rbac_get_basic_and_advanced(club)

    # Double check before creating
    if rbac_advanced:
        messages.error(
            request,
            "This club is already set up with advanced RBAC.",
            extra_tags="cobalt-message-error",
        )
    else:
        # set up advanced structure
        _admin_club_rbac_add_advanced_sub(club)

        # migrate across - any users get all access
        old_group_name = "rbac.orgs.clubs.generated.%s.%s.basic" % (
            club.state.lower(),
            club.id,
        )
        users = rbac_get_users_in_group_by_name(old_group_name)

        # add all users to all advanced groups. Admin can filter out later. This is the same access they had before
        for user in users:
            for rule in ORGS_RBAC_GROUPS_AND_ROLES:
                group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.{rule}")
                rbac_add_user_to_group(user, group)

        # delete basic
        rbac_delete_group_by_name(old_group_name)

        # Admin groups are the same whether basic or advanced so leave alone

        messages.success(
            request,
            "Club set up with Advanced RBAC. Check permissions, all users will have every access.",
            extra_tags="cobalt-message-success",
        )

    return redirect("organisations:admin_club_rbac", club_id=club.id)


@login_required()
def admin_club_rbac_convert_advanced_to_basic(request, club_id):
    """Change rbac setup for a club advanced -> basic"""

    # Get club
    club = get_object_or_404(Organisation, pk=club_id)

    has_access, role = _rbac_user_has_admin(club, request.user)
    if not has_access:
        return rbac_forbidden(request, role)

    # Check rbac setup
    rbac_basic, rbac_advanced = rbac_get_basic_and_advanced(club)

    # Double check before creating
    if rbac_basic:
        messages.error(
            request,
            "This club is already set up with basic RBAC.",
            extra_tags="cobalt-message-error",
        )
    else:
        # set up basic structure
        _admin_club_rbac_add_basic_sub(club)

        # migrate access across - any user goes into the one group
        # find the newly created basic group
        new_group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.basic")

        # Go through adding users from old structure to basic group and deleting old groups
        for rule in ORGS_RBAC_GROUPS_AND_ROLES:
            old_group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.{rule}")
            users = rbac_get_users_in_group(old_group)
            # Add all users to group
            for user in users:
                rbac_add_user_to_group(user, new_group)
            # delete group
            rbac_delete_group(old_group)

        # Admin groups are the same whether basic or advanced so leave alone

        messages.success(
            request,
            "Club changed to Basic RBAC.",
            extra_tags="cobalt-message-success",
        )

    return redirect("organisations:admin_club_rbac", club_id=club.id)
