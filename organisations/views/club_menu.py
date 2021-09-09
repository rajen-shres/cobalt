"""
Map

The entry point is club_menu() which loads the page menu.html
Menu.html uses HTMX to load the tab pages e.g. tab_dashboard_htmx()

"""
import codecs
import csv
import datetime
from copy import copy

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import validate_email
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.forms import UnregisteredUserForm
from accounts.models import User, UnregisteredUser
from accounts.views import invite_to_join
from cobalt.settings import GLOBAL_MPSERVER, GLOBAL_ORG, GLOBAL_TITLE, COBALT_HOSTNAME
from events.models import Congress
from masterpoints.views import abf_checksum_is_valid
from organisations.forms import (
    OrgForm,
    MembershipTypeForm,
    OrgDatesForm,
    MemberClubEmailForm,
    UserMembershipForm,
    UnregisteredUserAddForm,
    CSVUploadForm,
    MPCForm,
    TagForm,
)
from organisations.models import (
    ORGS_RBAC_GROUPS_AND_ROLES,
    Organisation,
    MembershipType,
    MemberMembershipType,
    MemberClubEmail,
    ClubLog,
    ClubTag,
    MemberClubTag,
)
from organisations.views.admin import (
    rbac_get_basic_and_advanced,
    get_secretary_from_org_form,
)
from organisations.views.general import (
    get_rbac_model_for_state,
    compare_form_with_mpc,
)
from payments.core import get_balance_and_recent_trans_org
from payments.models import MemberTransaction
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


def access_basic(request, club, message=None):  # sourcery skip: list-comprehension
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
    show_finance = uber_admin or rbac_user_has_role(
        request.user, f"payments.manage.{club.id}.view"
    )
    # Check if we show the congress tab
    show_congress = uber_admin or rbac_user_has_role(
        request.user, f"events.org.{club.id}.edit"
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
    elif rbac_advanced:
        return access_advanced(request, club)
    else:
        return HttpResponse(
            "<h3>This club has not been set up normally. Unable to manage access through the Club Menu.</h3>"
        )


@login_required()
def tab_dashboard_htmx(request):
    """build the dashboard tab in club menu"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

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


@login_required()
def tab_comms_email_htmx(request):
    """build the comms email tab in club menu"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    return render(
        request,
        "organisations/club_menu/comms/email_htmx.html",
        {"club": club},
    )


@login_required()
def tab_comms_tags_htmx(request):
    """build the comms tags tab in club menu"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    if "add" in request.POST:
        form = TagForm(request.POST)

        if form.is_valid():
            ClubTag.objects.get_or_create(
                organisation=club, tag_name=form.cleaned_data["tag_name"]
            )

    form = TagForm()

    tags = (
        ClubTag.objects.prefetch_related("memberclubtag_set")
        .filter(organisation=club)
        .order_by("tag_name")
    )

    # Add on count of how many members have this tag
    for tag in tags:
        uses = MemberClubTag.objects.filter(club_tag=tag).count()
        tag.uses = uses
        tag.hx_post = reverse("organisations:club_menu_tab_comms_tags_delete_tag_htmx")
        tag.hx_vars = f"club_id:{club.id},tag_id:{tag.id}"

    return render(
        request,
        "organisations/club_menu/comms/tags_htmx.html",
        {"club": club, "tags": tags, "form": form},
    )


@login_required()
def tab_comms_tags_delete_tag_htmx(request):
    """Delete a tag"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    tag_id = request.POST.get("tag_id")
    tag = get_object_or_404(ClubTag, pk=tag_id)
    if tag.organisation == club:
        tag.delete()

    return tab_comms_tags_htmx(request)


@login_required()
def tab_comms_tags_add_user_tag(request):
    """Add a tag to a user"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return HttpResponse("Error - Access denied")

    tag_id = request.POST.get("tag_id")
    tag = get_object_or_404(ClubTag, pk=tag_id)
    system_number = request.POST.get("system_number")

    if tag.organisation == club:
        MemberClubTag(club_tag=tag, system_number=system_number).save()
        return HttpResponse("Tag Added")

    return HttpResponse("Error")


@login_required()
def tab_comms_tags_remove_user_tag(request):
    """Remove a tag from a user"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return HttpResponse("Error - Access denied")

    tag_id = request.POST.get("tag_id")
    tag = get_object_or_404(ClubTag, pk=tag_id)
    system_number = request.POST.get("system_number")

    if tag.organisation == club:
        member_tag = MemberClubTag.objects.filter(
            club_tag=tag, system_number=system_number
        )
        member_tag.delete()
        return HttpResponse("Tag Removed")

    return HttpResponse("Error")


@login_required()
def tab_comms_public_info_htmx(request):
    """build the comms public info tab in club menu"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    return render(
        request,
        "organisations/club_menu/comms/public_info_htmx.html",
        {"club": club},
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
        "organisations/club_menu/congress/congress_htmx.html",
        {"club": club, "congresses": congresses},
    )


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


@login_required()
def tab_finance_htmx(request):
    """build the finance tab in club menu"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

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


@login_required()
def tab_members_list_htmx(request, message=None):
    """build the members tab in club menu"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    # Get System Numbers for All Members
    now = timezone.now()
    club_system_numbers = (
        MemberMembershipType.objects.filter(membership_type__organisation=club)
        .filter(start_date__lte=now)
        .filter(Q(end_date__gte=now) | Q(end_date=None))
        .values("system_number")
    )

    # Get real members
    cobalt_members = User.objects.filter(
        system_number__in=club_system_numbers
    ).order_by("last_name")

    # Get unregistered
    unregistered_members = UnregisteredUser.objects.filter(
        system_number__in=club_system_numbers
    ).order_by("last_name")

    total_members = cobalt_members.count() + unregistered_members.count()

    # Check level of access
    member_admin = rbac_user_has_role(request.user, f"orgs.members.{club.id}.edit")

    return render(
        request,
        "organisations/club_menu/members/list_htmx.html",
        {
            "club": club,
            "cobalt_members": cobalt_members,
            "unregistered_members": unregistered_members,
            "total_members": total_members,
            "message": message,
            "member_admin": member_admin,
        },
    )


@login_required()
def tab_members_add_htmx(request):
    """Add sub menu"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    total_members = _member_count(club)

    # Check level of access
    member_admin = rbac_user_has_role(request.user, f"orgs.members.{club.id}.edit")

    return render(
        request,
        "organisations/club_menu/members/add_menu_htmx.html",
        {
            "club": club,
            "total_members": total_members,
            "member_admin": member_admin,
        },
    )


@login_required()
def tab_members_reports_htmx(request):
    """Reports sub menu"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    # Check level of access
    member_admin = rbac_user_has_role(request.user, f"orgs.members.{club.id}.edit")

    return render(
        request,
        "organisations/club_menu/members/reports_htmx.html",
        {
            "club": club,
            "member_admin": member_admin,
        },
    )


@login_required()
def tab_members_report_all_csv(request, club_id):
    """CSV of all members"""

    club = get_object_or_404(Organisation, pk=club_id)

    # Check access
    allowed, role = _menu_rbac_has_access(club, request.user)
    if not allowed:
        return rbac_forbidden(request, role)

    # Get all ABF Numbers for members

    now = timezone.now()
    club_members = (
        MemberMembershipType.objects.filter(start_date__lte=now)
        .filter(Q(end_date__gte=now) | Q(end_date=None))
        .filter(membership_type__organisation=club)
    ).values_list("system_number")

    # Get proper users
    users = User.objects.filter(system_number__in=club_members)

    # Get un reg users
    un_regs = UnregisteredUser.objects.filter(system_number__in=club_members)

    # Get local emails (if set) and turn into a dictionary
    club_emails = MemberClubEmail.objects.filter(system_number__in=club_members)
    club_emails_dict = {}
    for club_email in club_emails:
        club_emails_dict[club_email.system_number] = club_email.email

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="members.csv"'

    writer = csv.writer(response)
    writer.writerow([club.name, f"Downloaded by {request.user.full_name}", now])
    writer.writerow(
        [
            f"{GLOBAL_ORG} Number",
            "First Name",
            "Last Name",
            "Email",
            "Email Source",
            f"{GLOBAL_TITLE} User Type",
            "Origin",
        ]
    )

    for user in users:

        writer.writerow(
            [
                user.system_number,
                user.first_name,
                user.last_name,
                user.email,
                "User",
                "Registered",
                "Self-registered",
            ]
        )

    for un_reg in un_regs:

        email = un_reg.email
        email_source = "Unregistered user"
        if un_reg.system_number in club_emails_dict:
            email = club_emails_dict[un_reg.system_number]
            email_source = "Club specific email"

        writer.writerow(
            [
                un_reg.system_number,
                un_reg.first_name,
                un_reg.last_name,
                email,
                email_source,
                "Unregistered",
                un_reg.origin,
            ]
        )

    return response


@login_required()
def tab_member_delete_un_reg_htmx(request, club_id, un_reg_id):
    """Remove an unregistered user from club membership"""

    club = get_object_or_404(Organisation, pk=club_id)
    un_reg = get_object_or_404(UnregisteredUser, pk=un_reg_id)

    # Check security
    allowed, role = _menu_rbac_has_access(club, request.user)
    if not allowed or not rbac_user_has_role(
        request.user, f"orgs.members.{club.id}.edit"
    ):
        return rbac_forbidden(request, role)

    # Memberships are coming later. For now we treat as basically binary - they start on the date they are
    # entered and we assume only one without checking
    now = timezone.now()
    memberships = (
        MemberMembershipType.objects.filter(start_date__lte=now)
        .filter(Q(end_date__gte=now) | Q(end_date=None))
        .filter(system_number=un_reg.system_number)
    )

    # Should only be one but not enforced at database level so close any that match to be safe
    for membership in memberships:
        membership.last_modified_by = request.user
        membership.termination_reason = "Cancelled by Club"
        membership.end_date = now - datetime.timedelta(days=1)
        membership.save()

        ClubLog(
            organisation=club,
            actor=request.user,
            action=f"Cancelled membership for {membership.system_number}",
        ).save()
    return tab_members_list_htmx(request, f"{un_reg.full_name} membership deleted.")


@login_required()
def tab_member_delete_member_htmx(request, club_id, member_id):
    """Remove a registered user from club membership"""

    club = get_object_or_404(Organisation, pk=club_id)
    member = get_object_or_404(User, pk=member_id)

    # Check security
    allowed, role = _menu_rbac_has_access(club, request.user)
    if not allowed or not rbac_user_has_role(
        request.user, f"orgs.members.{club.id}.edit"
    ):
        return rbac_forbidden(request, role)

    # Memberships are coming later. For now we treat as basically binary - they start on the date they are
    # entered and we assume only one without checking
    now = timezone.now()
    memberships = (
        MemberMembershipType.objects.filter(start_date__lte=now)
        .filter(Q(end_date__gte=now) | Q(end_date=None))
        .filter(system_number=member.system_number)
    )

    # Should only be one but not enforced at database level so close any that match to be safe
    for membership in memberships:
        membership.last_modified_by = request.user
        membership.termination_reason = "Cancelled by Club"
        membership.end_date = now - datetime.timedelta(days=1)
        membership.save()
        ClubLog(
            organisation=club,
            actor=request.user,
            action=f"Cancelled membership for {membership.system_number}",
        ).save()

    return tab_members_list_htmx(request, f"{member.full_name} membership deleted.")


@login_required()
def tab_members_un_reg_edit_htmx(request):
    """Edit unregistered member details"""

    status, error_page, club = _tab_is_okay(request)
    if not status or not rbac_user_has_role(
        request.user, f"orgs.members.{club.id}.edit"
    ):
        return error_page

    un_reg_id = request.POST.get("un_reg_id")
    un_reg = get_object_or_404(UnregisteredUser, pk=un_reg_id)
    # for later
    old_system_number = copy(un_reg.system_number)

    member_details = MemberMembershipType.objects.filter(
        system_number=un_reg.system_number
    ).first()
    message = ""

    if "save" in request.POST:
        user_form = UnregisteredUserForm(request.POST, instance=un_reg)
        club_email_form = MemberClubEmailForm(request.POST, prefix="club")

        # Assume the worst
        message = "Errors found on Form"

        if user_form.is_valid():
            new_un_reg = user_form.save()
            message = "Data Saved"
            ClubLog(
                organisation=club,
                actor=request.user,
                action=f"Updated details for {new_un_reg}",
            ).save()

            if "system_number" in user_form.changed_data:
                # We have updated the un_reg user, but we need to also change club email addresses,
                # and not just for this club

                ClubLog(
                    organisation=club,
                    actor=request.user,
                    action=f"Updated {GLOBAL_ORG} Number for {new_un_reg}",
                ).save()

                for email_match in MemberClubEmail.objects.filter(
                    system_number=old_system_number
                ):
                    email_match.system_number = new_un_reg.system_number
                    email_match.save()

                # reload un_reg
                un_reg = get_object_or_404(UnregisteredUser, pk=un_reg_id)

                # We also need to change club memberships
                for member_match in MemberMembershipType.objects.filter(
                    system_number=old_system_number
                ):
                    member_match.system_number = new_un_reg.system_number
                    member_match.save()

        if club_email_form.is_valid():
            club_email = club_email_form.cleaned_data["email"]
            club_email_entry, _ = MemberClubEmail.objects.get_or_create(
                organisation=club, system_number=un_reg.system_number
            )
            club_email_entry.email = club_email
            club_email_entry.save()
            message = "Data Saved"
            ClubLog(
                organisation=club,
                actor=request.user,
                action=f"Updated club email address for {un_reg}",
            ).save()

    else:
        club_email_entry = MemberClubEmail.objects.filter(
            organisation=club, system_number=un_reg.system_number
        ).first()
        user_form = UnregisteredUserForm(instance=un_reg)
        club_email_form = MemberClubEmailForm(prefix="club")

        # Set initial value for email if record exists
        if club_email_entry:
            club_email_form.initial["email"] = club_email_entry.email

    hx_delete = reverse(
        "organisations:club_menu_tab_member_delete_un_reg_htmx",
        kwargs={"club_id": club.id, "un_reg_id": un_reg.id},
    )

    member_tags = MemberClubTag.objects.prefetch_related("club_tag").filter(
        club_tag__organisation=club, system_number=un_reg.system_number
    )
    used_tags = member_tags.values("club_tag__tag_name")
    available_tags = ClubTag.objects.filter(organisation=club).exclude(
        tag_name__in=used_tags
    )

    return render(
        request,
        "organisations/club_menu/members/edit_un_reg_htmx.html",
        {
            "club": club,
            "un_reg": un_reg,
            "user_form": user_form,
            "club_email_form": club_email_form,
            "member_details": member_details,
            "member_tags": member_tags,
            "available_tags": available_tags,
            "hx_delete": hx_delete,
            "message": message,
        },
    )


@login_required()
@require_POST
def tab_members_add_member_htmx(request):
    """Add a club member manually"""

    status, error_page, club = _tab_is_okay(request)
    if not status or not rbac_user_has_role(
        request.user, f"orgs.members.{club.id}.edit"
    ):
        return error_page

    message = ""

    form = UserMembershipForm(request.POST, club=club)

    # Look for save as all requests are posts
    if "save" in request.POST:
        if form.is_valid():
            member_id = form.cleaned_data["member"]
            membership_type_id = form.cleaned_data["membership_type"]
            home_club = form.cleaned_data["home_club"]

            member = get_object_or_404(User, pk=member_id)
            membership_type = MembershipType(pk=membership_type_id)

            if MemberMembershipType.objects.filter(
                system_number=member.system_number, membership_type__organisation=club
            ).exists():
                form.add_error(
                    "member", f"{member.full_name} is already a member of this club"
                )
            else:
                MemberMembershipType(
                    system_number=member.system_number,
                    membership_type=membership_type,
                    last_modified_by=request.user,
                    home_club=home_club,
                ).save()
                message = f"{member.full_name} added as a member"
                ClubLog(
                    organisation=club,
                    actor=request.user,
                    action=f"Added member {member}",
                ).save()
                form = UserMembershipForm(club=club)
    else:
        form = UserMembershipForm(club=club)

    return render(
        request,
        "organisations/club_menu/members/add_member_htmx.html",
        {
            "club": club,
            "form": form,
            "message": message,
        },
    )


@login_required()
@require_POST
def tab_members_edit_member_htmx(request):
    """Edit a club member manually"""

    status, error_page, club = _tab_is_okay(request)
    if not status or not rbac_user_has_role(
        request.user, f"orgs.members.{club.id}.edit"
    ):
        return error_page

    message = ""

    member_id = request.POST.get("member")
    member = get_object_or_404(User, pk=member_id)

    # Look for save as all requests are posts
    if "save" in request.POST:
        form = UserMembershipForm(request.POST, club=club)

        if form.is_valid():

            # Get details
            membership_type_id = form.cleaned_data["membership_type"]
            membership_type = get_object_or_404(MembershipType, pk=membership_type_id)
            home_club = form.cleaned_data["home_club"]

            # Get the member membership objects
            member_membership = (
                MemberMembershipType.objects.filter(system_number=member.system_number)
                .filter(membership_type__organisation=club)
                .first()
            )

            # Update and save
            member_membership.membership_type = membership_type
            member_membership.home_club = home_club
            member_membership.save()
            message = f"{member.full_name} updated"
            ClubLog(
                organisation=club,
                actor=request.user,
                action=f"Edited details for member {member}",
            ).save()
            return tab_members_list_htmx(request, message)

        else:
            print(form.errors)
    else:
        member_membership = (
            MemberMembershipType.objects.filter(system_number=member.system_number)
            .filter(membership_type__organisation=club)
            .first()
        )
        initial = {
            "member": member.id,
            "membership_type": member_membership.membership_type.id,
            "home_club": member_membership.home_club,
        }
        form = UserMembershipForm(club=club)
        form.initial = initial

    hx_delete = reverse(
        "organisations:club_menu_tab_member_delete_member_htmx",
        kwargs={"club_id": club.id, "member_id": member.id},
    )

    member_tags = MemberClubTag.objects.prefetch_related("club_tag").filter(
        club_tag__organisation=club, system_number=member.system_number
    )
    used_tags = member_tags.values("club_tag__tag_name")
    available_tags = ClubTag.objects.filter(organisation=club).exclude(
        tag_name__in=used_tags
    )

    return render(
        request,
        "organisations/club_menu/members/edit_member_htmx.html",
        {
            "club": club,
            "form": form,
            "member": member,
            "message": message,
            "hx_delete": hx_delete,
            "member_tags": member_tags,
            "available_tags": available_tags,
        },
    )


@login_required()
@require_POST
def tab_members_add_un_reg_htmx(request):
    """Add a club unregistered user manually"""

    status, error_page, club = _tab_is_okay(request)
    if not status or not rbac_user_has_role(
        request.user, f"orgs.members.{club.id}.edit"
    ):
        return error_page

    message = ""

    if "save" in request.POST:

        form = UnregisteredUserAddForm(request.POST, club=club)

        # Assume the worst
        message = "Errors found on Form"

        # Set up to rollback if we fail
        #    point_in_time = transaction.savepoint()

        if form.is_valid():
            # User may already be registered, the form will allow this
            if UnregisteredUser.objects.filter(
                system_number=form.cleaned_data["system_number"],
            ).exists():
                message = "User already existed."  # don't change the fields
            else:
                UnregisteredUser(
                    system_number=form.cleaned_data["system_number"],
                    last_updated_by=request.user,
                    last_name=form.cleaned_data["last_name"],
                    first_name=form.cleaned_data["first_name"],
                    email=form.cleaned_data["mpc_email"],
                    origin="Manual",
                    added_by_club=club,
                ).save()
                ClubLog(
                    organisation=club,
                    actor=request.user,
                    action=f"Added un-registered user {form.cleaned_data['first_name']} {form.cleaned_data['last_name']}",
                ).save()
                message = "User added."

            # Add to club
            if MemberMembershipType.objects.filter(
                system_number=form.cleaned_data["system_number"],
                membership_type__organisation=club,
            ).exists():
                message += " Already a member of club."
            else:
                MemberMembershipType.objects.get_or_create(
                    system_number=form.cleaned_data["system_number"],
                    membership_type_id=form.cleaned_data["membership_type"],
                    home_club=form.cleaned_data["home_club"],
                    last_modified_by=request.user,
                )
                message += " Club membership added."

            # Add email
            club_email = form.cleaned_data["club_email"]
            if club_email:
                club_email_entry, _ = MemberClubEmail.objects.get_or_create(
                    organisation=club, system_number=form.cleaned_data["system_number"]
                )
                club_email_entry.email = club_email
                club_email_entry.save()
                ClubLog(
                    organisation=club,
                    actor=request.user,
                    action=f"Added club specific email for {form.cleaned_data['system_number']}",
                ).save()

                message += " Club specific email added."

            # return blank form to add another
            form = UnregisteredUserAddForm(club=club)

    else:
        form = UnregisteredUserAddForm(club=club)

    return render(
        request,
        "organisations/club_menu/members/add_un_reg_htmx.html",
        {
            "club": club,
            "form": form,
            "message": message,
        },
    )


@login_required()
def tab_forums_htmx(request):
    """build the forums tab in club menu"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    return render(
        request, "organisations/club_menu/forums/forums_htmx.html", {"club": club}
    )


@login_required()
def tab_results_htmx(request):
    """build the results tab in club menu"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    return render(
        request, "organisations/club_menu/results/results_htmx.html", {"club": club}
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

            ClubLog(
                organisation=club, actor=request.user, action="Updated club details"
            ).save()

            # We can't use Django messages as they won't show until the whole page reloads
            message = "Organisation details updated"

    org_form = compare_form_with_mpc(org_form, club)

    # secretary is a bit fiddly so we pass as a separate thing
    secretary_id, secretary_name = get_secretary_from_org_form(org_form)

    # Check if this user is state or global admin - then they can change the State or org_id
    uber_admin = _user_is_uber_admin(club, request.user)

    return render(
        request,
        "organisations/club_menu/settings/basic_htmx.html",
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
    ClubLog(
        organisation=club,
        actor=request.user,
        action="Reloaded data from Masterpoints Centre",
    ).save()

    return tab_settings_basic_htmx(request)


@login_required()
def tab_settings_logs_htmx(request):
    """Reload data from MPC and return the settings basic tab"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    log_events = ClubLog.objects.filter(organisation=club).order_by("-action_date")

    return render(
        request,
        "organisations/club_menu/settings/logs_htmx.html",
        {"log_events": log_events},
    )


@login_required()
def tab_settings_general_htmx(request):
    """build the settings tab in club menu for editing general details"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    message = ""

    # This is a POST even the first time so look for "save" to see if this really is a form submit
    real_post = "save" in request.POST

    if not real_post:
        form = OrgDatesForm(instance=club)
    else:
        form = OrgDatesForm(request.POST, instance=club)

        if form.is_valid():
            org = form.save(commit=False)
            org.last_updated_by = request.user
            org.last_updated = timezone.localtime()
            org.save()

            ClubLog(
                organisation=club, actor=request.user, action="Updated general settings"
            ).save()

            # We can't use Django messages as they won't show until the whole page reloads
            message = "Organisation details updated"

    return render(
        request,
        "organisations/club_menu/settings/general_htmx.html",
        {
            "club": club,
            "form": form,
            "message": message,
        },
    )


@login_required()
def tab_settings_membership_htmx(request):
    """build the settings tab in club menu for editing membership types"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    membership_types = MembershipType.objects.filter(organisation=club)

    return render(
        request,
        "organisations/club_menu/settings/membership_htmx.html",
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

    # This is a POST even the first time so look for "save" to see if this really is a form submit
    real_post = "save" in request.POST

    if not real_post:
        form = MembershipTypeForm(instance=membership_type)
    else:
        form = MembershipTypeForm(request.POST, instance=membership_type)

    message = ""

    if form.is_valid():
        updated = form.save(commit=False)
        updated.last_modified_by = request.user
        updated.save()
        ClubLog(
            organisation=club,
            actor=request.user,
            action=f"Updated membership type: {updated}",
        ).save()
        message = "Membership Type Updated"

    # Don't show option to set as default if there is already a default, unless we are it
    if (
        MembershipType.objects.filter(organisation=club, is_default=True)
        .exclude(pk=membership_type.id)
        .exists()
    ):
        del form.fields["is_default"]

    return render(
        request,
        "organisations/club_menu/settings/membership_edit_htmx.html",
        {
            "club": club,
            "membership_type": membership_type,
            "form": form,
            "message": message,
        },
    )


@login_required()
def club_menu_tab_settings_membership_add_htmx(request):
    """Part of the settings tab for membership types to allow user to add a membership type"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    # This is a POST even the first time so look for "save" to see if this really is a form submit
    real_post = "save" in request.POST

    form = MembershipTypeForm(request.POST) if real_post else MembershipTypeForm()
    message = ""

    if form.is_valid():
        membership_type = form.save(commit=False)
        membership_type.last_modified_by = request.user
        membership_type.organisation = club
        membership_type.save()
        ClubLog(
            organisation=club,
            actor=request.user,
            action=f"Added membership type: {membership_type.name}",
        ).save()
        return tab_settings_membership_htmx(request)

    # Don't show option to set as default if there is already a default
    if MembershipType.objects.filter(organisation=club, is_default=True).exists():
        del form.fields["is_default"]

    return render(
        request,
        "organisations/club_menu/settings/membership_add_htmx.html",
        {
            "club": club,
            "form": form,
            "message": message,
        },
    )


@login_required()
def club_menu_tab_settings_membership_delete_htmx(request):
    """Part of the settings tab for membership types to allow user to delete a membership type"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    # Get membership type id
    membership_type_id = request.POST.get("membership_type_id")
    membership_type = get_object_or_404(MembershipType, pk=membership_type_id)

    # Check for active members in this membership type
    now = timezone.now()
    if (
        MemberMembershipType.objects.filter(membership_type=membership_type)
        .filter(start_date__lte=now)
        .filter(Q(end_date__gte=now) | Q(end_date=None))
        .exists()
    ):
        return HttpResponse(
            f"<h2 class='text-center'>Cannot Delete {membership_type.name}</h2> "
            f"<h3 class='text-center'>There Are Active Members Here</h3> "
            f"<p class='text-center'>Change members membership types first.</p>."
        )

    # The first time we show a confirmation
    if "delete" not in request.POST:
        return render(
            request,
            "organisations/club_menu/settings/membership_delete_confirm_htmx.html",
            {"membership_type": membership_type},
        )
    else:
        membership_type.delete()

    return tab_settings_membership_htmx(request)


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

    return access_basic(request, club)


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


def _club_menu_tab_members_upload_csv_pianola(club_member):
    """Pianola specific formatting for CSV files

    Args:
        club_member: list (a row from spreadsheet)

    Returns:
        Bool: True for success, False for failure
        error: message describing error (if there was one)
        item: dict with formatted values

    """

    # Skip visitors, at least for now
    if club_member[21].find("Visitor") >= 0:
        return False, f"{club_member[1]} - skipped visitor", None
    item = {
        "system_number": club_member[1],
        "first_name": club_member[5],
        "last_name": club_member[6],
        "email": club_member[7],
    }

    return True, None, item


def _club_menu_tab_members_upload_csv_generic(club_member):
    """formatting for Generic CSV files

    Args:
        club_member: list (a row from spreadsheet)

    Returns:
        Bool: True for success, False for failure
        error: message describing error (if there was one)
        item: dict with formatted values

    """

    item = {
        "system_number": club_member[0],
        "first_name": club_member[1],
        "last_name": club_member[2],
        "email": club_member[3],
    }

    return True, None, item


def _club_menu_tab_members_upload_cs2_generic(club_member):
    """formatting for Compscore 2 files

    Args:
        club_member: list (a row from spreadsheet)

    Returns:
        Bool: True for success, False for failure
        error: message describing error (if there was one)
        item: dict with formatted values

    """

    item = {
        "system_number": club_member[8],
        "first_name": club_member[1].capitalize(),
        "last_name": club_member[0].capitalize(),
        "email": club_member[7],
    }

    return True, None, item


def _club_menu_tab_members_upload_csv_common(item):
    """Common checks for all formats

    Args:
        item: dict

    Returns:
        Bool: True for success, False for failure
        error: message describing error (if there was one)
        item: dict with formatted values

    """

    system_number = item["system_number"]
    first_name = item["first_name"]
    last_name = item["last_name"]
    email = item["email"]

    system_number = system_number.strip()

    try:
        system_number = int(system_number)
    except ValueError:
        return False, f"{system_number} - invalid {GLOBAL_ORG} Number", None

    # Basic validation

    # TODO: Checking with MPC is too slow. We just validate the checksum
    #  if not check_system_number(system_number):
    if not abf_checksum_is_valid(system_number):
        return False, f"{system_number} - invalid {GLOBAL_ORG} Number", None

    if len(first_name) < 1:
        return False, f"{system_number} - First name missing", None

    if len(last_name) < 1:
        return False, f"{system_number} - Last name missing", None

    if email:
        try:
            validate_email(email)
        except ValidationError:
            return False, f"{system_number} - Invalid email {email}", None

    item = {
        "system_number": system_number,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
    }

    return True, None, item


def club_menu_tab_members_upload_csv_htmx(request):
    """Upload CSV"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    # no files - show form
    if not request.FILES:
        form = CSVUploadForm(club=club)
        return render(
            request, "organisations/club_menu/members/csv_htmx.html", {"form": form}
        )

    form = CSVUploadForm(request.POST, club=club)
    form.is_valid()
    csv_errors = []

    # Get params
    csv_file = request.FILES["file"]
    file_type = form.cleaned_data["file_type"]
    membership_type = form.cleaned_data["membership_type"]
    home_club = form.cleaned_data["home_club"]

    default_membership = get_object_or_404(MembershipType, pk=membership_type)

    # get CSV reader (convert bytes to strings)
    csv_data = csv.reader(codecs.iterdecode(csv_file, "utf-8"))

    # skip header
    next(csv_data, None)

    # Process data
    member_data = []

    for club_member in csv_data:

        # Specific formatting and tests by format
        if file_type == "Pianola":
            rc, error, item = _club_menu_tab_members_upload_csv_pianola(club_member)
        elif file_type == "CSV":
            rc, error, item = _club_menu_tab_members_upload_csv_generic(club_member)
        elif file_type == "CS2":
            rc, error, item = _club_menu_tab_members_upload_cs2_generic(club_member)
        else:
            raise ImproperlyConfigured

        if not rc:
            csv_errors.append(error)
            continue

        # Common checks
        rc, error, item = _club_menu_tab_members_upload_csv_common(item)

        if not rc:
            csv_errors.append(error)
            continue

        member_data.append(item)

    added_users, added_unregistered_users, errors = process_member_import(
        club=club,
        member_data=member_data,
        user=request.user,
        origin=file_type,
        default_membership=default_membership,
        home_club=home_club,
        club_specific_email=True,
    )

    # Build results table
    table = render_to_string(
        "organisations/club_menu/members/table_htmx.html",
        {
            "added_users": added_users,
            "added_unregistered_users": added_unregistered_users,
            "errors": errors + csv_errors,
        },
    )

    ClubLog(
        organisation=club,
        actor=request.user,
        action=f"Uploaded member data from CSV file. Type={file_type}",
    ).save()

    return tab_members_list_htmx(request, table)


def club_menu_tab_members_import_mpc_htmx(request):
    """Import Data from the Masterpoints Centre.

    We connect directly to the MPC to get members for this club.

    Members can be home members or alternate members (members of the club but this
    isn't their home club so ABF and State fees are not charged for them.

    There is no visitor information in the MPC, that happens at the club level.

    """

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

    if "save" not in request.POST:
        form = CSVUploadForm(club=club)
        return render(
            request,
            "organisations/club_menu/members/mpc_htmx.html",
            {"form": form, "club": club},
        )

    form = MPCForm(request.POST, club=club)
    form.is_valid()

    membership_type = form.cleaned_data["membership_type"]
    default_membership = get_object_or_404(MembershipType, pk=membership_type)

    # Get home club members from MPC
    qry = f"{GLOBAL_MPSERVER}/clubMemberList/{club.org_id}"
    club_members = masterpoint_query(qry)

    member_data = [
        {
            "system_number": club_member["ABFNumber"],
            "first_name": club_member["GivenNames"],
            "last_name": club_member["Surname"],
            "email": club_member["EmailAddress"],
        }
        for club_member in club_members
    ]

    (
        home_added_users,
        home_added_unregistered_users,
        home_errors,
    ) = process_member_import(
        club=club,
        member_data=member_data,
        user=request.user,
        origin="MPC",
        default_membership=default_membership,
        club_specific_email=False,
        home_club=True,
    )

    # Get Alternate (non-home) club members from MPC
    qry = f"{GLOBAL_MPSERVER}/clubAltMemberList/{club.org_id}"
    club_members = masterpoint_query(qry)

    member_data = [
        {
            "system_number": club_member["ABFNumber"],
            "first_name": club_member["GivenNames"],
            "last_name": club_member["Surname"],
            "email": club_member["EmailAddress"],
        }
        for club_member in club_members
    ]

    alt_added_users, alt_added_unregistered_users, away_errors = process_member_import(
        club=club,
        member_data=member_data,
        user=request.user,
        origin="MPC",
        default_membership=default_membership,
        club_specific_email=False,
        home_club=False,
    )

    errors = home_errors + away_errors
    registered_added = home_added_users + alt_added_users
    unregistered_added = home_added_unregistered_users + alt_added_unregistered_users

    # Build results table
    table = render_to_string(
        "organisations/club_menu/members/table_htmx.html",
        {
            "added_users": registered_added,
            "added_unregistered_users": unregistered_added,
            "errors": errors,
        },
    )

    ClubLog(
        organisation=club,
        actor=request.user,
        action="Imported member data from the Masterpoints Centre",
    ).save()

    return tab_members_list_htmx(request, table)


def process_member_import_add_member_to_membership(
    club: Organisation,
    club_member: dict,
    user: User,
    default_membership: MembershipType,
    home_club: bool = False,
):
    """Sub process to add a member to the member-membership model. Returns 0 if already there
    or 1 for counting purposes, plus an error or warning if one is found"""

    error = None
    now = timezone.now()
    name = f"{club_member['system_number']} - {club_member['first_name']} {club_member['last_name']}"

    print(now)

    # Check if already there
    member_membership = (
        MemberMembershipType.objects.filter(system_number=club_member["system_number"])
        .filter(membership_type__organisation=club)
        .filter(start_date__lte=now)
        .filter(Q(end_date__gte=now) | Q(end_date=None))
        .first()
    )
    print("got member_membership", member_membership)

    if member_membership:
        # check for other home clubs
        other_home_club = (
            MemberMembershipType.objects.filter(
                system_number=club_member["system_number"]
            )
            .exclude(membership_type__organisation=club)
            .filter(start_date__lte=now)
            .filter(Q(end_date__gte=now) | Q(end_date=None))
            .exists()
        )

        error = f"{name} - Already a member"

        if other_home_club and home_club:
            error = f"{name} - Already a member and has a different home club"
        elif home_club:
            member_membership.home_club = home_club
            member_membership.save()
        return 0, error

    # check for other home clubs before setting this as the users home club
    other_home_club = (
        MemberMembershipType.objects.filter(system_number=club_member["system_number"])
        .filter(start_date__lte=now)
        .filter(Q(end_date__gte=now) | Q(end_date=None))
        .exists()
    )

    print("Got other home club 2 ", other_home_club)

    print("home club", home_club)

    if home_club and other_home_club:
        error = f"{name} - Added but already has a home club"
        home_club = False

    MemberMembershipType(
        membership_type=default_membership,
        system_number=club_member["system_number"],
        last_modified_by=user,
        home_club=home_club,
    ).save()
    return 1, error


def process_member_import(
    club: Organisation,
    member_data: list,
    user: User,
    origin: str,
    default_membership: MembershipType,
    home_club: bool = False,
    club_specific_email: bool = False,
):
    """Common function to process a list of members

    Args:
        default_membership: Which membership to add this user to
        club_specific_email: Is this email specific to this club? True for 'club' sources like Pianola, False for MPC
        home_club: Is this the home club for this user
        origin: Where did we get this data from?
        user: Logged in user who is making this change
        member_data: list of data
        club: Club object

    """

    # counters
    added_users = 0
    added_unregistered_users = 0
    errors = []

    # loop through members
    for club_member in member_data:

        # See if we have an actual user for this
        user_match = User.objects.filter(
            system_number=club_member["system_number"]
        ).first()

        if user_match:
            added, error = process_member_import_add_member_to_membership(
                club, club_member, user, default_membership, home_club
            )
            added_users += added
            if error:
                errors.append(error)
        else:
            # See if we have an unregistered user already
            un_reg = UnregisteredUser.objects.filter(
                system_number=club_member["system_number"]
            ).first()

            if not un_reg:
                # Create a new unregistered user

                # Check if this email should be added to user or just this club
                email = None if club_specific_email else club_member["email"]

                UnregisteredUser(
                    system_number=club_member["system_number"],
                    first_name=club_member["first_name"],
                    last_name=club_member["last_name"],
                    email=email,
                    origin=origin,
                    last_updated_by=user,
                    added_by_club=club,
                ).save()

            # add to club email list if required - don't override if already present
            if (
                club_specific_email
                and not MemberClubEmail.objects.filter(
                    organisation=club,
                    system_number=club_member["system_number"],
                ).exists()
            ):
                MemberClubEmail(
                    organisation=club,
                    system_number=club_member["system_number"],
                    email=club_member["email"],
                ).save()

            added, error = process_member_import_add_member_to_membership(
                club, club_member, user, default_membership, home_club
            )

            added_unregistered_users += added
            if error:
                errors.append(error)

    return added_users, added_unregistered_users, errors


def invite_user_to_join_htmx(request):
    """Invite an unregistered user to sign up"""

    status, error_page, club = _tab_is_okay(request)
    if not status:
        return error_page

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
        return tab_members_list_htmx(
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

    return tab_members_list_htmx(request, f"Invite sent to {un_reg.full_name}")
