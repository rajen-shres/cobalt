import csv
from datetime import date, timedelta
import logging
from itertools import chain

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, HttpRequest
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone

import organisations.views.club_menu_tabs.utils
from accounts.views.admin import invite_to_join
from accounts.views.core import add_un_registered_user_with_mpc_data
from accounts.views.api import search_for_user_in_cobalt_and_mpc
from accounts.forms import UnregisteredUserForm
from accounts.models import User, UnregisteredUser, UserAdditionalInfo
from club_sessions.models import SessionEntry
from cobalt.settings import (
    GLOBAL_ORG,
    GLOBAL_TITLE,
    COBALT_HOSTNAME,
    GLOBAL_CURRENCY_SYMBOL,
)
from masterpoints.views import (
    search_mpc_users_by_name,
    user_summary,
)
from masterpoints.factories import masterpoint_query_row
from notifications.models import UnregisteredBlockedEmail, BatchID
from notifications.views.core import (
    custom_sender,
    send_cobalt_email_with_template,
    create_rbac_batch_id,
    club_default_template,
    get_emails_sent_to_address,
)
from organisations.club_admin_core import (
    add_member,
    can_perform_action,
    change_membership,
    club_email_for_member,
    club_has_unregistered_members,
    get_club_members,
    get_club_member_list,
    get_club_member_list_email_match,
    get_contact_system_numbers,
    get_member_count,
    get_member_details,
    get_member_log,
    get_member_system_numbers,
    get_outstanding_memberships,
    get_valid_actions,
    get_valid_activities,
    log_member_change,
    make_membership_payment,
    member_details_description,
    member_details_short_description,
    perform_simple_action,
    renew_membership,
    MEMBERSHIP_STATES_TERMINAL,
)
from organisations.decorators import check_club_menu_access
from organisations.forms import (
    MemberClubEmailForm,
    UserMembershipForm,
    UnregisteredUserAddForm,
    UnregisteredUserMembershipForm,
    MemberClubDetailsForm,
    MembershipExtendForm,
    MembershipChangeTypeForm,
    MembershipPaymentForm,
    MembershipRawEditForm,
)
from organisations.models import (
    MemberMembershipType,
    Organisation,
    MemberClubEmail,
    MemberClubOptions,
    ClubLog,
    MemberClubTag,
    ClubTag,
    MembershipType,
    WelcomePack,
    OrgEmailTemplate,
    MiscPayType,
)
from organisations.views.general import (
    get_rbac_model_for_state,
)
from payments.models import (
    MemberTransaction,
    UserPendingPayment,
    OrgPaymentMethod,
)
from payments.views.core import (
    get_balance,
    org_balance,
    update_account,
    update_organisation,
)
from payments.views.payments_api import payment_api_batch
from rbac.core import rbac_user_has_role
from post_office.models import Email as PostOfficeEmail

from rbac.views import rbac_forbidden
from utils.utils import cobalt_currency, cobalt_paginator

logger = logging.getLogger("cobalt")


@check_club_menu_access()
def list_htmx(request: HttpRequest, club: Organisation, message: str = None):
    """build the members tab in club menu"""

    DEFAULT_SORT = "last_desc"

    def save_sort_order(new_order):
        """Save the selected sort order"""
        additional_info = UserAdditionalInfo.objects.filter(user=request.user).last()
        if additional_info:
            if additional_info.member_sort_order != new_order:
                additional_info.member_sort_order = new_order
                additional_info.save()
        elif new_order != DEFAULT_SORT:
            additional_info = UserAdditionalInfo()
            additional_info.user = request.user
            additional_info.member_sort_order = new_order
            additional_info.save()

    # get sort options, could be POST or GET
    sort_option = request.GET.get("sort_by")
    if not sort_option:
        sort_option = request.POST.get("sort_by")
        if not sort_option:
            additional_info = UserAdditionalInfo.objects.filter(
                user=request.user
            ).last()
            if additional_info and additional_info.member_sort_order:
                sort_option = additional_info.member_sort_order
            else:
                sort_option = "last_desc"
        else:
            save_sort_order(sort_option)
    else:
        save_sort_order(sort_option)

    #  show former members
    former_members = request.POST.get("former_members") == "on"

    members = get_club_members(
        club,
        sort_option=sort_option,
        active_only=not former_members,
        exclude_deceased=not former_members,
    )

    # pagination and params
    things = cobalt_paginator(request, members)
    searchparams = f"sort_by={sort_option}&"

    total_members = len(members)

    # Check level of access
    member_admin = rbac_user_has_role(request.user, f"orgs.members.{club.id}.edit")

    has_errors = _check_member_errors(club)

    hx_post = reverse("organisations:club_menu_tab_members_htmx")

    return render(
        request,
        "organisations/club_menu/members/list_htmx.html",
        {
            "club": club,
            "things": things,
            "total_members": total_members,
            "message": message,
            "member_admin": member_admin,
            "has_errors": has_errors,
            "hx_post": hx_post,
            "searchparams": searchparams,
            "sort_option": sort_option,
            "former_members": former_members,
            "full_membership_mgmt": club.full_club_admin,
        },
    )


@check_club_menu_access()
def add_htmx(request, club, message=None):
    """Add sub menu"""

    if not MembershipType.objects.filter(organisation=club).exists():
        return HttpResponse(
            "<h4>Your club has no membership types defined. You cannot add a member until you fix this.</h4>"
        )

    total_members = get_member_count(club)

    # Check level of access
    member_admin = rbac_user_has_role(request.user, f"orgs.members.{club.id}.edit")

    has_errors = _check_member_errors(club)

    return render(
        request,
        "organisations/club_menu/members/add_menu_htmx.html",
        {
            "club": club,
            "total_members": total_members,
            "member_admin": member_admin,
            "has_errors": has_errors,
            "has_unregistered": club_has_unregistered_members(club),
            "message": message,
            "full_membership_mgmt": club.full_club_admin,
        },
    )


@check_club_menu_access()
def reports_htmx(request, club):
    """Reports sub menu"""

    # Check level of access
    member_admin = rbac_user_has_role(request.user, f"orgs.members.{club.id}.edit")

    has_errors = _check_member_errors(club)

    return render(
        request,
        "organisations/club_menu/members/reports_htmx.html",
        {
            "club": club,
            "member_admin": member_admin,
            "has_errors": has_errors,
            "full_membership_mgmt": club.full_club_admin,
        },
    )


@login_required()
def club_admin_report_all_csv(request, club_id):
    """CSV of all members. We can't use the decorator as I can't get HTMX to treat this as a CSV"""

    # Get all ABF Numbers for members

    club = get_object_or_404(Organisation, pk=club_id)

    # Check for club level access - most common
    club_role = f"orgs.members.{club.id}.edit"
    if not rbac_user_has_role(request.user, club_role):

        # Check for state level access or global
        rbac_model_for_state = get_rbac_model_for_state(club.state)
        state_role = f"orgs.state.{rbac_model_for_state}.edit"
        if not rbac_user_has_role(request.user, state_role) and not rbac_user_has_role(
            request.user, "orgs.admin.edit"
        ):
            return rbac_forbidden(request, club_role)

    # get members
    club_members = get_club_members(club, active_only=False)

    # create dict of system number to membership type name
    membership_type_dict = {}
    club_members_list = []
    for club_member in club_members:
        system_number = club_member.system_number
        membership_type = club_member.latest_membership.membership_type.name
        membership_type_dict[system_number] = membership_type
        club_members_list.append(system_number)

    # Get tags and turn into dictionary
    tags = MemberClubTag.objects.filter(
        system_number__in=club_members_list, club_tag__organisation=club
    )
    tags_dict = {}
    for tag in tags:
        if tag.system_number not in tags_dict:
            tags_dict[tag.system_number] = []
        tags_dict[tag.system_number].append(tag.club_tag.tag_name)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="members.csv"'

    now = timezone.now()

    writer = csv.writer(response)
    writer.writerow([club.name, f"Downloaded by {request.user.full_name}", now])
    writer.writerow(
        [
            f"{GLOBAL_ORG} Number",
            "Club Membership Number",
            "First Name",
            "Last Name",
            f"{GLOBAL_TITLE} User Type",
            "Membership Type",
            "Membership Status",
            "Membership Start Date",
            "Membership End Date",
            "Paid Unit Date",
            "Due Date",
            "Auto Pay Date",
            "Paid Date",
            "Fee",
            "Email",
            "Joined Date",
            "Left Date",
            "Address 1",
            "Address 2",
            "State",
            "Post Code",
            "Mobile",
            "Other Phone",
            "Date of Birth",
            "Emergency Contact",
            "Tags",
            "Notes",
        ]
    )

    def format_date_or_none(a_date):
        return a_date.strftime("%d/%m/%Y") if a_date else ""

    for member in club_members:
        member_tags = tags_dict.get(member.system_number, "")

        writer.writerow(
            [
                member.system_number,
                member.club_membership_number,
                member.first_name,
                member.last_name,
                member.user_type,
                membership_type_dict.get(member.system_number, ""),
                member.get_membership_status_display(),
                format_date_or_none(member.latest_membership.start_date),
                format_date_or_none(member.latest_membership.end_date),
                format_date_or_none(member.latest_membership.paid_until_date),
                format_date_or_none(member.latest_membership.due_date),
                format_date_or_none(member.latest_membership.auto_pay_date),
                format_date_or_none(member.latest_membership.paid_date),
                member.latest_membership.fee,
                member.email,
                format_date_or_none(member.joined_date),
                format_date_or_none(member.left_date),
                member.address1,
                member.address2,
                member.state,
                member.postcode,
                member.mobile,
                member.other_phone,
                member.dob,
                member.emergency_contact,
                member_tags,
                member.notes,
            ]
        )

    return response


# JPG deprecated - replaced
@login_required()
def report_all_csv(request, club_id):
    """CSV of all members. We can't use the decorator as I can't get HTMX to treat this as a CSV"""

    # Get all ABF Numbers for members

    club = get_object_or_404(Organisation, pk=club_id)

    # Check for club level access - most common
    club_role = f"orgs.members.{club.id}.edit"
    if not rbac_user_has_role(request.user, club_role):

        # Check for state level access or global
        rbac_model_for_state = get_rbac_model_for_state(club.state)
        state_role = f"orgs.state.{rbac_model_for_state}.edit"
        if not rbac_user_has_role(request.user, state_role) and not rbac_user_has_role(
            request.user, "orgs.admin.edit"
        ):
            return rbac_forbidden(request, club_role)

    # Get club members
    now = timezone.now()
    club_members = (
        MemberMembershipType.objects.filter(start_date__lte=now).filter(
            membership_type__organisation=club
        )
    ).values("system_number", "membership_type__name")

    # create dict of system number to membership type
    membership_type_dict = {}
    club_members_list = []
    for club_member in club_members:
        system_number = club_member["system_number"]
        membership_type = club_member["membership_type__name"]
        membership_type_dict[system_number] = membership_type
        club_members_list.append(system_number)

    # Get proper users
    users = User.objects.filter(system_number__in=club_members_list)

    # Get un reg users
    un_regs = UnregisteredUser.objects.filter(system_number__in=club_members_list)

    # Get local emails (if set) and turn into a dictionary
    club_emails = MemberClubEmail.objects.filter(system_number__in=club_members_list)
    club_emails_dict = {
        club_email.system_number: club_email.email for club_email in club_emails
    }

    # Get tags and turn into dictionary
    tags = MemberClubTag.objects.filter(
        system_number__in=club_members_list, club_tag__organisation=club
    )
    tags_dict = {}
    for tag in tags:
        if tag.system_number not in tags_dict:
            tags_dict[tag.system_number] = []
        tags_dict[tag.system_number].append(tag.club_tag.tag_name)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="members.csv"'

    writer = csv.writer(response)
    writer.writerow([club.name, f"Downloaded by {request.user.full_name}", now])
    writer.writerow(
        [
            f"{GLOBAL_ORG} Number",
            "First Name",
            "Last Name",
            "Membership Type",
            "Email",
            "Email Source",
            f"{GLOBAL_TITLE} User Type",
            "Origin",
            "Tags",
        ]
    )

    for user in users:
        user_tags = tags_dict.get(user.system_number, "")
        writer.writerow(
            [
                user.system_number,
                user.first_name,
                user.last_name,
                membership_type_dict.get(user.system_number, ""),
                # Don't include email addresses for registered users
                "-",
                # user.email,
                "User",
                "Registered",
                "Self-registered",
                user_tags,
            ]
        )

    for un_reg in un_regs:

        email = "-"
        email_source = "-"
        if un_reg.system_number in club_emails_dict:
            email = club_emails_dict[un_reg.system_number]
            email_source = "Unregistered User"

        user_tags = tags_dict.get(un_reg.system_number, "")
        writer.writerow(
            [
                un_reg.system_number,
                un_reg.first_name,
                un_reg.last_name,
                membership_type_dict.get(un_reg.system_number, ""),
                email,
                email_source,
                "Unregistered",
                un_reg.origin,
                user_tags,
            ]
        )

    return response


def _cancel_membership(request, club, system_number):
    """Common function to cancel membership"""

    # Memberships are coming later. For now we treat as basically binary - they start on the date they are
    # entered and we assume only one without checking
    memberships = MemberMembershipType.objects.filter(
        system_number=system_number
    ).filter(membership_type__organisation=club)

    # Should only be one but not enforced at database level so close any that match to be safe
    for membership in memberships:
        membership.delete()

        ClubLog(
            organisation=club,
            actor=request.user,
            action=f"Cancelled membership for {system_number}",
        ).save()

    # Delete any tags
    MemberClubTag.objects.filter(club_tag__organisation=club).filter(
        system_number=system_number
    ).delete()

    # Remove any email addresses for this club and user
    MemberClubEmail.objects.filter(
        organisation=club, system_number=system_number
    ).delete()


@check_club_menu_access(check_members=True)
def delete_un_reg_htmx(request, club):
    """Remove an unregistered user from club membership"""

    un_reg = get_object_or_404(UnregisteredUser, pk=request.POST.get("un_reg_id"))
    _cancel_membership(request, club, un_reg.system_number)

    return list_htmx(request, message=f"{un_reg.full_name} membership deleted.")


@check_club_menu_access(check_members=True)
def delete_member_htmx(request, club):
    """Remove a registered user from club membership"""

    member = get_object_or_404(User, pk=request.POST.get("member_id"))
    _cancel_membership(request, club, member.system_number)

    return list_htmx(request, message=f"{member.full_name} membership deleted.")


# JPG deprecate
def _un_reg_edit_htmx_process_form(
    request, un_reg, club, membership, user_form, club_email_form, club_membership_form
):
    """Sub process to handle form for un_reg_edit_htmx"""

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

    if club_membership_form.is_valid():
        membership.home_club = club_membership_form.cleaned_data["home_club"]
        membership_type = MembershipType.objects.get(
            pk=club_membership_form.cleaned_data["membership_type"]
        )
        membership.membership_type = membership_type
        membership.save()

        message = "Data Saved"
        ClubLog(
            organisation=club,
            actor=request.user,
            action=f"Updated details for {membership.system_number}",
        ).save()

    if club_email_form.is_valid():
        club_email = club_email_form.cleaned_data["email"]

        # If the club email was used but is now empty, delete the record
        if not club_email:
            club_email_entry = MemberClubEmail.objects.filter(
                organisation=club, system_number=un_reg.system_number
            )
            if club_email_entry:
                club_email_entry.delete()
                message = "Local email address deleted"
                ClubLog(
                    organisation=club,
                    actor=request.user,
                    action=f"Removed club email address for {un_reg}",
                ).save()

        else:

            # See if we have an email for this user and club
            club_email_entry = MemberClubEmail.objects.filter(
                organisation=club, system_number=un_reg.system_number
            ).first()
            if not club_email_entry:
                club_email_entry = MemberClubEmail(
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

            # See if we have a bounce on this user and clear it
            if club_email_entry.email_hard_bounce:
                club_email_entry.email_hard_bounce = False
                club_email_entry.email_hard_bounce_reason = None
                club_email_entry.email_hard_bounce_date = None
                club_email_entry.save()

                ClubLog(
                    organisation=club,
                    actor=request.user,
                    action=f"Cleared email hard bounce for {un_reg} by editing email address",
                ).save()

    return message, un_reg, membership


# JPG deprecate
def _un_reg_edit_htmx_common(
    request,
    club,
    un_reg,
    message,
    user_form,
    club_email_form,
    club_membership_form,
    member_details,
    club_email_entry,
):
    """Common part of editing un registered user, used whether form was filled in or not"""

    member_tags = MemberClubTag.objects.prefetch_related("club_tag").filter(
        club_tag__organisation=club, system_number=un_reg.system_number
    )
    used_tags = member_tags.values("club_tag__tag_name")
    available_tags = ClubTag.objects.filter(organisation=club).exclude(
        tag_name__in=used_tags
    )

    email_address = club_email_for_member(club, un_reg.system_number)

    emails = get_emails_sent_to_address(email_address, club, request.user)

    # See if there are blocks on either email address - we don't just look for this user
    if club_email_entry:
        private_email_blocked = UnregisteredBlockedEmail.objects.filter(
            email=club_email_entry.email
        ).exists()
    else:
        private_email_blocked = False

    return render(
        request,
        "organisations/club_menu/members/edit_un_reg_htmx.html",
        {
            "club": club,
            "un_reg": un_reg,
            "user_form": user_form,
            "club_email_form": club_email_form,
            "club_membership_form": club_membership_form,
            "member_details": member_details,
            "member_tags": member_tags,
            "available_tags": available_tags,
            "hx_delete": reverse(
                "organisations:club_menu_tab_member_delete_un_reg_htmx"
            ),
            "hx_args": f"club_id:{club.id},un_reg_id:{un_reg.id}",
            "message": message,
            "email_address": email_address,
            "emails": emails,
            "private_email_blocked": private_email_blocked,
        },
    )


# JPG deprecate ?
@check_club_menu_access(check_members=True)
def un_reg_edit_htmx(request, club):
    """Edit unregistered member details"""

    un_reg_id = request.POST.get("un_reg_id")
    un_reg = get_object_or_404(UnregisteredUser, pk=un_reg_id)

    # Get first membership record for this user and this club
    membership = MemberMembershipType.objects.filter(
        system_number=un_reg.system_number, membership_type__organisation=club
    ).first()

    message = ""
    club_email_entry = None

    if "save" in request.POST:
        # We got form data - process it
        user_form = UnregisteredUserForm(request.POST, instance=un_reg)
        club_email_form = MemberClubEmailForm(request.POST, prefix="club")
        club_membership_form = UnregisteredUserMembershipForm(
            request.POST, club=club, system_number=un_reg.system_number, prefix="member"
        )

        message, un_reg, membership = _un_reg_edit_htmx_process_form(
            request,
            un_reg,
            club,
            membership,
            user_form,
            club_email_form,
            club_membership_form,
        )

    else:
        # No form data so build up what we need to show user
        club_email_entry = MemberClubEmail.objects.filter(
            organisation=club, system_number=un_reg.system_number
        ).first()
        user_form = UnregisteredUserForm(instance=un_reg)
        club_email_form = MemberClubEmailForm(prefix="club")
        club_membership_form = UnregisteredUserMembershipForm(
            club=club, system_number=un_reg.system_number, prefix="member"
        )

        # Set initial values for membership form
        #        club_membership_form.initial["home_club"] = membership.home_club
        if membership:
            club_membership_form.initial[
                "membership_type"
            ] = membership.membership_type_id

        # Set initial value for email if record exists
        if club_email_entry:
            club_email_form.initial["email"] = club_email_entry.email

    # Common parts
    return _un_reg_edit_htmx_common(
        request,
        club,
        un_reg,
        message,
        user_form,
        club_email_form,
        club_membership_form,
        membership,
        club_email_entry,
    )


@check_club_menu_access(check_members=True)
def add_member_htmx(request, club):
    """Add a club member manually. This is called by the add_any page and return the list page.
    This shouldn't get errors so we don't return a form, we just use the message field if
    we do get an error and return the list view.
    """

    message = ""

    form = UserMembershipForm(request.POST, club=club)

    if form.is_valid():

        # get data from form
        system_number = int(form.cleaned_data["system_number"])
        membership_type_id = form.cleaned_data["membership_type"]
        home_club = form.cleaned_data["home_club"]
        send_welcome_pack = form.cleaned_data.get("send_welcome_email")

        member = User.objects.filter(system_number=system_number).first()
        membership_type = MembershipType(pk=membership_type_id)

        if MemberMembershipType.objects.filter(
            system_number=member.system_number,
            membership_type__organisation=club,
        ).exists():
            # shouldn't happen, but just in case
            message = f"{member.full_name} is already a member of this club"
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

        if send_welcome_pack:
            resp = _send_welcome_pack(
                club, member.first_name, member.email, request.user, False
            )
            message = f"{message}. {resp}"
    else:
        print(form.errors)

    return list_htmx(request, message=message)


def _send_welcome_pack(club, first_name, email, user, invite_to_join):
    """Send a welcome pack"""
    welcome_pack = WelcomePack.objects.filter(organisation=club).first()

    if not welcome_pack:
        return "No welcome pack found."

    if invite_to_join:
        register = reverse("accounts:register")
        email_body = f"""{welcome_pack.welcome_email}
        <br<br>
        <p>You are not yet a member of {GLOBAL_TITLE}. <a href="http://{COBALT_HOSTNAME}{register}">Visit us to join for free</a>.</p>
        """
    else:
        email_body = welcome_pack.welcome_email

    context = {
        "name": first_name,
        "title": f"Welcome to {club}!",
        "email_body": email_body,
    }

    # Get the extra fields from the template if we have one
    # Use a reasonable club default if possible, otherwise a general default
    use_template = (
        welcome_pack.template
        or club_default_template(club)
        or OrgEmailTemplate(organisation=club)
    )

    reply_to = use_template.reply_to
    from_name = use_template.from_name
    if use_template.banner:
        context["img_src"] = use_template.banner.url
        #  JPG debug
        # print(f"++++++ _send_welcome_pack url={use_template.banner.url}")

    context["footer"] = use_template.footer

    if use_template.box_colour:
        context["box_colour"] = use_template.box_colour

    if use_template.box_font_colour:
        context["box_font_colour"] = use_template.box_font_colour

    # sender = f"{from_name}<donotreply@myabf.com.au>" if from_name else None
    sender = custom_sender(from_name)

    # Create batch id to allow any admin for this club to view the email
    batch_id = create_rbac_batch_id(
        rbac_role=f"notifications.orgcomms.{club.id}.edit",
        user=user,
        organisation=club,
        batch_type=BatchID.BATCH_TYPE_COMMS,
        batch_size=1,
        description=context["title"],
        complete=True,
    )

    send_cobalt_email_with_template(
        to_address=email,
        context=context,
        batch_id=batch_id,
        template="system - club",
        reply_to=reply_to,
        sender=sender,
    )

    return "Welcome email sent."


@check_club_menu_access(check_members=True)
def add_any_member_htmx(request, club):
    """Add a club member manually"""

    member_form = UserMembershipForm(club=club)
    un_reg_form = UnregisteredUserAddForm(club=club)
    welcome_pack = WelcomePack.objects.filter(organisation=club).exists()

    return render(
        request,
        "organisations/club_menu/members/add_any_member_htmx.html",
        {
            "club": club,
            "member_form": member_form,
            "un_reg_form": un_reg_form,
            "welcome_pack": welcome_pack,
        },
    )


@login_required()
def add_member_search_htmx(request):
    """Search function for adding a member (registered, unregistered or from MPC)

    This is also borrowed by the edit_session_entry screen in club_sessions to change
    the user. They set a flag, so we can use their template instead of ours.

    """

    # JPG to do - review use by club_sessions. Note addition of 'contact' user source

    first_name_search = request.POST.get("member_first_name_search")
    last_name_search = request.POST.get("member_last_name_search")
    club_id = request.POST.get("club_id")

    # Things from our friends at club_sessions
    edit_session_entry = request.POST.get("edit_session_entry")
    session_id = request.POST.get("session_id")
    session_entry_id = request.POST.get("session_entry_id")

    # if there is nothing to search for, don't search
    if not first_name_search and not last_name_search:
        return HttpResponse()

    user_list, is_more = search_for_user_in_cobalt_and_mpc(
        first_name_search, last_name_search
    )

    # Now highlight users who are already club members
    user_list_system_numbers = [user["system_number"] for user in user_list]

    club = get_object_or_404(Organisation, pk=club_id)

    member_list = get_member_system_numbers(club, target_list=user_list_system_numbers)
    contact_list = get_contact_system_numbers(
        club, target_list=user_list_system_numbers
    )

    for user in user_list:
        if user["system_number"] in member_list:
            user["source"] = "member"
        elif user["system_number"] in contact_list:
            user["source"] = "contact"

    if edit_session_entry:
        template = "club_sessions/manage/edit_entry/member_search_results_htmx.html"
    else:
        template = "organisations/club_menu/members/member_search_results_htmx.html"

    return render(
        request,
        template,
        {
            "user_list": user_list,
            "is_more": is_more,
            "edit_session_entry": edit_session_entry,
            "club_id": club_id,
            "session_id": session_id,
            "session_entry_id": session_entry_id,
        },
    )


# JPG deprecated
@check_club_menu_access(check_members=True)
def edit_member_htmx(request, club, message=""):
    """Edit a club member manually"""

    # JPG debug
    print("*** edit_member_htmx ***")

    member_id = request.POST.get("member")
    member = get_object_or_404(User, pk=member_id)

    # Look for save as all requests are posts
    if "save" in request.POST:

        message = _edit_member_htmx_save(request, club, member)

    form = _edit_member_htmx_default(club, member)

    # Add on common parts

    hx_delete = reverse("organisations:club_menu_tab_member_delete_member_htmx")
    hx_vars = f"club_id:{club.id},member_id:{member.id}"

    # Get member tags
    member_tags = MemberClubTag.objects.prefetch_related("club_tag").filter(
        club_tag__organisation=club, system_number=member.system_number
    )
    used_tags = member_tags.values("club_tag__tag_name")
    available_tags = ClubTag.objects.filter(organisation=club).exclude(
        tag_name__in=used_tags
    )

    # Get recent emails too
    # if rbac_user_has_role(
    #     request.user, f"notifications.orgcomms.{club.id}.edit"
    # ) or rbac_user_has_role(request.user, "orgs.admin.edit"):
    #     emails = PostOfficeEmail.objects.filter(to=[member.email]).order_by("-pk")[:20]
    # else:
    #     emails = None

    # JPG cleanup

    emails = get_emails_sent_to_address(member.email, club, request.user)

    # Get payment stuff
    recent_payments, misc_payment_types = _get_misc_payment_vars(member, club)

    # Get any outstanding debts
    user_pending_payments = UserPendingPayment.objects.filter(
        system_number=member.system_number
    )

    # augment data
    for user_pending_payment in user_pending_payments:

        if user_pending_payment.organisation == club:

            user_pending_payment.can_delete = True
            user_pending_payment.hx_delete = reverse(
                "organisations:club_menu_tab_finance_cancel_user_pending_debt_htmx"
            )
            user_pending_payment.hx_vars = f"club_id:{club.id}, user_pending_payment_id:{user_pending_payment.id}, member:{member.id}, return_member_tab:1"

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

    # JPG clean up - note this only handles User members
    # Get augmented membership details
    membership_details = get_member_details(club, member.system_number)

    return render(
        request,
        "organisations/club_menu/members/edit_member_htmx.html",
        {
            "club": club,
            "form": form,
            "member": member,
            "message": message,
            "hx_delete": hx_delete,
            "hx_vars": hx_vars,
            "member_tags": member_tags,
            "available_tags": available_tags,
            "emails": emails,
            "recent_payments": recent_payments,
            "user_pending_payments": user_pending_payments,
            "misc_payment_types": misc_payment_types,
            "user_balance": user_balance,
            "club_balance": club_balance,
            "user_has_payments_edit": user_has_payments_edit,
            "user_has_payments_view": user_has_payments_view,
            "membership_details": membership_details,
            "terminal_states": MEMBERSHIP_STATES_TERMINAL,
        },
    )


# JPG clean-up deprecated - replaced by club_admin.py activity_emails_html
@check_club_menu_access(check_members=True)
def get_recent_emails_htmx(request, club):
    """Delayed load of recent emails for the member detail view"""

    member_id = request.POST.get("member_id")
    member = get_object_or_404(User, pk=member_id)

    emails = get_emails_sent_to_address(member.email, club, request.user)

    return render(
        request,
        "organisations/club_menu/members/recent_emails.html",
        {
            "club": club,
            "member": member,
            "emails": emails,
        },
    )


# JPG deprecated
def _get_misc_payment_vars(member, club):
    """get variables relating to this members misc payments for this club"""

    # Get recent misc payments
    recent_payments = MemberTransaction.objects.filter(
        member=member, organisation=club
    ).order_by("-created_date")[:10]

    # get this orgs miscellaneous payment types
    misc_payment_types = MiscPayType.objects.filter(organisation=club)

    return recent_payments, misc_payment_types


# JPG deprecated ?
def _edit_member_htmx_save(request, club, member):
    """sub for edit_member_htmx to handle getting a real POST"""

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

    else:
        # Very unlikely
        print(form.errors)
        message = f"Errors on form: {form.errors}"

    return message


def _edit_member_htmx_default(club, member):
    """sub of edit_member_htmx for when we don't get a POST."""

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

    return form


@check_club_menu_access(check_members=True)
def add_un_reg_htmx(request, club):
    """Add a club unregistered user manually. This is called by the add_any page and return the list page.
    This shouldn't get errors so we don't return a form, we just use the message field if
    we do get an error and return the list view.
    """

    message = ""

    # We are adding this person as a member of this club, they may or may not already be set up as unregistered users

    form = UnregisteredUserAddForm(request.POST, club=club)

    if not form.is_valid():
        message = "An error occurred while trying to add a member. "
        for error in form.errors:
            message += error
        return list_htmx(request, message=message)

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
        MemberMembershipType(
            system_number=form.cleaned_data["system_number"],
            membership_type_id=form.cleaned_data["membership_type"],
            home_club=form.cleaned_data["home_club"],
            last_modified_by=request.user,
        ).save()
        message += " Club membership added."

    # Add email
    club_email = form.cleaned_data["club_email"]
    if club_email and club_email != "":
        MemberClubEmail(
            organisation=club,
            system_number=form.cleaned_data["system_number"],
            email=club_email,
        ).save()
        ClubLog(
            organisation=club,
            actor=request.user,
            action=f"Added club specific email for {form.cleaned_data['system_number']}",
        ).save()

        message += " Club specific email added."

    if form.cleaned_data.get("send_welcome_email"):

        email_address = form.cleaned_data["mpc_email"]
        if email_address:
            resp = _send_welcome_pack(
                club,
                form.cleaned_data["first_name"],
                email_address,
                request.user,
                True,
            )
            message = f"{message} {resp}"
        else:
            message += " Welcome email not sent, no email provided."

    # club is added to the call by the decorator
    return list_htmx(request, message=message)


def _check_member_errors(club):
    """Check if there are any errors such as bounced email addresses"""

    members_system_numbers = MemberMembershipType.objects.filter(
        membership_type__organisation=club,
    ).values_list("system_number")

    # Check for bounced status. For registered users this is stored on a separate table,
    # for unregistered it is on the club email table
    users = User.objects.filter(system_number__in=members_system_numbers).filter(
        useradditionalinfo__email_hard_bounce=True
    )
    un_regs_bounces = (
        MemberClubEmail.objects.filter(organisation=club)
        .filter(email_hard_bounce=True)
        .values("system_number")
    )
    un_regs = UnregisteredUser.objects.filter(system_number__in=un_regs_bounces)

    return list(chain(users, un_regs))


@check_club_menu_access(check_members=True)
def errors_htmx(request, club):
    """Show errors tab (only shows if errors present)"""

    has_errors = _check_member_errors(club)

    # Check level of access
    member_admin = rbac_user_has_role(request.user, f"orgs.members.{club.id}.edit")

    return render(
        request,
        "organisations/club_menu/members/errors_htmx.html",
        {
            "has_errors": has_errors,
            "member_admin": member_admin,
            "club": club,
            "full_membership_mgmt": club.full_club_admin,
        },
    )


# JPG depratce - moved to club_admin common
@check_club_menu_access(check_session_or_payments=True)
def add_misc_payment_htmx(request, club):
    """Adds a miscellaneous payment for a user. Could be the club charging them, or the club paying them"""

    # load data from form
    misc_description = request.POST.get("misc_description")
    member = get_object_or_404(User, pk=request.POST.get("member_id"))
    amount = float(request.POST.get("amount"))
    charge_or_pay = request.POST.get("charge_or_pay")

    if amount <= 0:
        misc_message = "Amount must be greater than zero"

    if charge_or_pay == "charge":
        misc_message = _add_misc_payment_charge(
            request, club, member, amount, misc_description
        )
    else:
        misc_message = add_misc_payment_pay(
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
        "organisations/club_menu/members/edit_member_payments_htmx.html",
        {
            "club": club,
            "member": member,
            "misc_message": misc_message,
            "recent_payments": recent_payments,
            "misc_payment_types": misc_payment_types,
            "user_balance": user_balance,
            "club_balance": club_balance,
            "user_has_payments_edit": user_has_payments_edit,
        },
    )


# JPG deprecate
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


@check_club_menu_access(check_session_or_payments=True)
def get_member_balance_htmx(request, club):
    """Show balance for this user"""

    member_id = request.POST.get("member")
    if not member_id:
        return HttpResponse("No member found in request")

    member = get_object_or_404(User, pk=member_id)

    return HttpResponse(f"${get_balance(member):,.2f}")


def add_misc_payment_pay(request, club, member, amount, misc_description):
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


#  jpg clean-up
# @check_club_menu_access(check_members=True)
# def member_search_tab_htmx(request, club):
#     """member search tab"""

#     member_admin = rbac_user_has_role(request.user, f"orgs.members.{club.id}.edit")

#     return render(
#         request,
#         "organisations/club_menu/members/member_search_tab_htmx.html",
#         {"member_admin": member_admin, "club": club},
#     )


# @check_club_menu_access()
# def member_search_tab_name_htmx(request, club):
#     """Search function for searching for a member by name"""

#     first_name_search = request.POST.get("member_first_name_search")
#     last_name_search = request.POST.get("member_last_name_search")

#     # if there is nothing to search for, don't search
#     if not first_name_search and not last_name_search:
#         return HttpResponse()

#     member_list = get_club_member_list(club)

#     # Users
#     users = User.objects.filter(system_number__in=member_list)

#     if first_name_search:
#         users = users.filter(first_name__istartswith=first_name_search)

#     if last_name_search:
#         users = users.filter(last_name__istartswith=last_name_search)

#     # Unregistered
#     un_regs = UnregisteredUser.objects.filter(system_number__in=member_list)

#     if first_name_search:
#         un_regs = un_regs.filter(first_name__istartswith=first_name_search)

#     if last_name_search:
#         un_regs = un_regs.filter(last_name__istartswith=last_name_search)

#     user_list = list(chain(users, un_regs))

#     return render(
#         request,
#         "organisations/club_menu/members/member_search_tab_name_htmx.html",
#         {"user_list": user_list, "club": club},
#     )


# @check_club_menu_access()
# def member_search_tab_email_htmx(request, club):
#     """Search function for searching for a member by email"""

#     email_search = request.POST.get("member_email_search")

#     # if there is nothing to search for, don't search
#     if not email_search:
#         return HttpResponse()

#     member_club_system_number_list = get_club_member_list_email_match(club, email_search)

#     # JPG clean up
#     # Unregistered Only
#     # member_club_system_number_list = (
#     #     MemberClubEmail.objects.filter(email__icontains=email_search)
#     #     .filter(organisation=club)
#     #     .values("system_number")
#     # )

#     un_regs = UnregisteredUser.objects.filter(
#         system_number__in=member_club_system_number_list
#     )

#     return render(
#         request,
#         "organisations/club_menu/members/member_search_tab_name_htmx.html",
#         {"user_list": un_regs, "club": club},
#     )


@check_club_menu_access(check_members=True)
def bulk_invite_to_join_htmx(request, club):
    """Invite multiple people to join MyABF"""

    members = MemberMembershipType.objects.filter(
        membership_type__organisation=club
    ).values("system_number")
    unregistered = UnregisteredUser.objects.filter(system_number__in=members)

    two_weeks = timezone.now() - timezone.timedelta(weeks=2)

    can_invite = unregistered.filter(
        Q(last_registration_invite_sent__lte=two_weeks)
        | Q(last_registration_invite_sent=None)
    )
    cannot_invite = unregistered.filter(last_registration_invite_sent__gt=two_weeks)

    if "send_invites" in request.POST:

        success = 0
        failure = 0

        for member in can_invite:
            club_email = club_email_for_member(club, member.system_number)
            if club_email and invite_to_join(member, club_email, request.user, club):
                success += 1
            else:
                failure += 1
        if failure > 0:
            return HttpResponse(f"<h3>{success} Invites sent. {failure} Failures.</h3>")
        else:
            return HttpResponse(f"<h3>{success} Invites sent</h3>")

    return render(
        request,
        "organisations/club_menu/members/bulk_invite_to_join_htmx.html",
        {"can_invite": can_invite, "cannot_invite": cannot_invite},
    )


@check_club_menu_access(check_members=True)
def unblock_unreg_email_address_htmx(request, club):
    """remove the block on an unregistered user email address"""

    email = request.POST.get("email")
    blocked = UnregisteredBlockedEmail.objects.filter(email=email).first()
    if blocked:
        blocked.delete()
        return HttpResponse("<h3 class='text-primary'>Block removed</h3>")
    else:
        return HttpResponse("<h3 class='text-primary'>Email address not found</h3>")


@check_club_menu_access(check_members=True)
def recent_sessions_for_member_htmx(request, club):
    """Show recent sessions for a member"""

    member = get_object_or_404(User, pk=request.POST.get("member_id"))
    sessions = (
        SessionEntry.objects.filter(system_number=member.system_number)
        .order_by("-session__session_date")
        .select_related("session")
    )

    things = cobalt_paginator(request, sessions, 2)

    # Add hx_post for paginator controls
    hx_post = reverse(
        "organisations:club_menu_tab_members_recent_sessions_for_member_htmx"
    )
    hx_vars = f"club_id:{club.id}, member_id:{member.id}"
    hx_target = "#recent_sessions"

    return render(
        request,
        "organisations/club_menu/members/recent_sessions_for_member_htmx.html",
        {
            "club": club,
            "member": member,
            "things": things,
            "hx_post": hx_post,
            "hx_vars": hx_vars,
            "hx_target": hx_target,
        },
    )


# ----------------------------------------------------------------------------------
# Club admin - Edit member
# ----------------------------------------------------------------------------------


@check_club_menu_access(check_members=True)
def club_admin_edit_member_htmx(request, club, message=None):
    """
    Edit member for full club admin, htmx endpoint version

    Called with club_id and system_number in the POST (note only POST methods accepted)
    """

    system_number = request.POST.get("system_number", None)
    post_message = request.POST.get("message", None)
    if message and post_message:
        message = f"{message}. {post_message}"
    elif post_message:
        message = post_message
    saving = request.POST.get("save", "NO") == "YES"
    editing = request.POST.get("edit", "NO") == "YES"
    show_history = request.POST.get("show_history", "NO") == "YES"

    if not system_number:
        # JPG to do - this call will not work. perhaps raise an exception instead
        return list_htmx(request, message="System number required")

    member_details = get_member_details(club, system_number)

    valid_actions = get_valid_actions(member_details)

    #  check whether always sharing profile data

    if member_details.user_type == f"{GLOBAL_TITLE} User":
        user = User.objects.get(pk=member_details.user_or_unreg_id)
        club_options = MemberClubOptions.objects.filter(
            club=club,
            user=user,
        ).last()
        always_shared = (
            club_options
            and club_options.share_data == MemberClubOptions.SHARE_DATA_ALWAYS
        )
    else:
        always_shared = False

    # JPG Debug
    print(f"**** always shared = {always_shared}")

    # get the members complete set of memberships
    member_history = (
        MemberMembershipType.objects.filter(
            system_number=system_number,
            membership_type__organisation=club,
        )
        .select_related("membership_type")
        .order_by("-created_at")
    )

    # work out the index of the current membership for highlighting
    # in the history list

    current_index = None
    for index, mmt in enumerate(member_history):
        if mmt == member_details.latest_membership:
            current_index = index
            break

    # get the members log history
    log_history = get_member_log(club, system_number)

    if request.POST.get("save", "NO") == "LOG":

        if request.POST.get("log_entry", None):

            # JPG to do: clean text

            # log it
            log_member_change(
                club,
                system_number,
                request.user,
                request.POST.get("log_entry"),
            )
            message = "Comment added to the log"

        else:
            message = "Nothing added, type a comment then click Add"

    if member_details.user_type == f"{GLOBAL_TITLE} User":

        # Get any outstanding debts
        user_pending_payments = UserPendingPayment.objects.filter(
            system_number=system_number
        )

        # augment data
        for user_pending_payment in user_pending_payments:

            if user_pending_payment.organisation == club:

                user_pending_payment.can_delete = True
                user_pending_payment.hx_delete = reverse(
                    "organisations:club_menu_tab_finance_cancel_user_pending_debt_htmx"
                )
                user_pending_payment.hx_vars = f"club_id:{club.id}, user_pending_payment_id:{user_pending_payment.id}, member:{member_details.user_or_unreg_id}, return_member_tab:1"

    else:
        user_pending_payments = None

    if saving:
        form = MemberClubDetailsForm(request.POST, instance=member_details)
        if form.is_valid():
            form.save()
            message = "Updates saved"
        else:
            message = "Error saving updates"
            editing = True

    else:
        form = MemberClubDetailsForm(instance=member_details)

    # member_description = member_details_description(member_details)
    member_description = member_details_short_description(member_details)

    # which recent activities should be shown?
    permitted_activities = get_valid_activities(member_details)

    # Note: member_admin is used in conditioning the member nav area.
    # The user has this access if they have got this far.

    return render(
        request,
        "organisations/club_menu/members/club_admin_edit_member_htmx.html",
        {
            "club": club,
            "member_details": member_details,
            "member_history": member_history,
            "current_index": current_index,
            "log_history": log_history[:20],
            "form": form,
            "valid_actions": valid_actions,
            "message": message,
            "member_admin": True,
            "user_pending_payments": user_pending_payments,
            "edit_details": editing,
            "member_description": member_description,
            "system_number": member_details.system_number,
            "permitted_activities": permitted_activities,
            "show_history": show_history,
            "full_membership_mgmt": club.full_club_admin,
            "always_shared": always_shared,
        },
    )


# ----------------------------------------------------------------------------------
# Club admin - Edit member - Action button end points
#
#   Simple actions are all handled through one end point which gets the action
#   name from the request:
#       club_admin_edit_member_membership_action_htmx
#
#   More complex actions which require a view to be presented to get additional
#   parameters require their own end points (and url path entries)
# ----------------------------------------------------------------------------------


def _refresh_edit_member(request, club, system_number, message, show_history=False):
    """Refreshes the edit member view from within the view
    ie. call as the result of an htmx end point to refresh the view
    """

    return render(
        request,
        "organisations/club_menu/members/club_admin_edit_member_refresh_htmx.html",
        {
            "club_id": club.id,
            "system_number": system_number,
            "message": message,
            "show_history_str": "YES" if show_history else "NO",
        },
    )


def _refresh_member_list(request, club):
    """Refreshes the member list view from within the view
    ie. call as the result of an htmx end point to refresh the view
    """

    return render(
        request,
        "organisations/club_menu/members/club_admin_member_list_refresh_htmx.html",
        {
            "club_id": club.id,
        },
    )


@check_club_menu_access(check_members=True)
def club_admin_edit_member_change_htmx(request, club):
    """HTMX endpoint to change a member to a new membership type.
    Displays and processes a form to get the new type and related attributes.
    Redirects to reload the main edit member view on completion or fatal error.

    Args:
        request (HttpRequest): the request
        club_id (int): the club's Organisation id
        system_number (int): the member's system number

    Returns:
        HttpResponse: the response
    """

    system_number = request.POST.get("system_number")

    member_details = get_member_details(club, system_number)

    permitted_action, message = can_perform_action("change", member_details)
    if not permitted_action:
        # refresh view with error
        return _refresh_edit_member(
            request,
            club,
            system_number,
            message if message else "Action not permitted",
        )

    # Build the list of available membership types, and associated default fees and dates.
    # When the user selects a type in the form the corresponding fee and dates need to be set
    # Note: end_date is not set for types which do not renew (eg Life membership)
    # Note: values are converted to types that JavaScript can ingest
    # Note: allow a change to the same type to allow details to be changed
    membership_types = (
        MembershipType.objects.filter(organisation=club)
        .exclude(id=member_details.latest_membership.membership_type.id)
        .all()
    )
    membership_choices = [(mt.id, mt.name) for mt in membership_types]
    today = timezone.now().date()
    fees_and_due_dates = {
        f"{mt.id}": {
            "annual_fee": float(mt.annual_fee),
            "due_date": (today + timedelta(mt.grace_period_days)).strftime("%Y-%m-%d"),
            "end_date": " "
            if mt.does_not_renew
            else club.current_end_date.strftime("%Y-%m-%d"),
            "perpetual": "Y" if mt.does_not_renew else "N",
        }
        for mt in membership_types
    }

    if len(membership_choices) == 0:
        # no choices so go back to the main view

        return _refresh_edit_member(
            request,
            club,
            system_number,
            "Unable to change type, no alternatives available",
        )

    if "save" in request.POST:
        form = MembershipChangeTypeForm(
            request.POST,
            club=club,
            registered=(member_details.user_type == f"{GLOBAL_TITLE} User"),
        )
        if form.is_valid():

            membership_type = get_object_or_404(
                MembershipType, pk=int(form.cleaned_data["membership_type"])
            )

            # post logic
            success, message = change_membership(
                club,
                system_number,
                membership_type,
                request.user,
                fee=form.cleaned_data["fee"],
                start_date=form.cleaned_data["start_date"],
                end_date=form.cleaned_data["end_date"],
                due_date=form.cleaned_data["due_date"],
                payment_method_id=int(form.cleaned_data["payment_method"]),
                process_payment=True,
            )

            if success:

                return _refresh_edit_member(
                    request,
                    club,
                    system_number,
                    message if message else "Membership type changed",
                )

    else:
        initial_data = {
            "membership_type": membership_choices[0][0],
            "start_date": today.strftime("%Y-%m-%d"),
            "payment_method": -1,
            # JPG clean up
            # "end_date": club.current_end_date.strftime("%Y-%m-%d"),
            # "fee": fees_and_due_dates[f"{membership_choices[0][0]}"]['annual_fee'],
            # "due_date": fees_and_due_dates[f"{membership_choices[0][0]}"]['due_date'],
            # "is_paid": False,
        }
        form = MembershipChangeTypeForm(
            initial=initial_data,
            club=club,
            registered=(member_details.user_type == f"{GLOBAL_TITLE} User"),
        )

    return render(
        request,
        "organisations/club_menu/members/club_admin_edit_member_change_htmx.html",
        {
            "club": club,
            "system_number": system_number,
            "form": form,
            "fees_and_dates": f"{fees_and_due_dates}",
            "message": message,
        },
    )


@check_club_menu_access(check_members=True)
def club_admin_edit_member_membership_action_htmx(request, club):
    """Common end point for all simple membership actions

    The member's system number and action name are passed in the
    request POST. The updated is attempted and the member edit view
    is refreshed with the new state or an error message.
    """

    system_number = request.POST.get("system_number", None)
    action_name = request.POST.get("action_name", None)

    if not system_number or not action_name:
        message = "Error - system number or action missing"
    else:
        success, message = perform_simple_action(
            action_name, club, system_number, requester=request.user
        )

    if success and action_name == "delete":
        # member is now a contact so can't refresh the member edit view

        return _refresh_member_list(request, club)

    return _refresh_edit_member(
        request,
        club,
        system_number,
        message,
    )


@check_club_menu_access(check_members=True)
def club_admin_edit_member_payment_htmx(request, club):
    """
    Get payment details
    """

    system_number = request.POST.get("system_number", None)
    member_details = get_member_details(club, system_number)

    membership_to_pay = get_outstanding_memberships(
        club,
        system_number,
    ).last()

    if not membership_to_pay:
        # nothing to pay, should not have been called

        return _refresh_edit_member(
            request,
            club,
            system_number,
            "No membership fees to pay",
        )

    message = None

    if "save" in request.POST:

        form = MembershipPaymentForm(
            request.POST,
            club=club,
            registered=(member_details.user_type == f"{GLOBAL_TITLE} User"),
        )

        form.is_valid()

        payment_success, payment_message = make_membership_payment(
            club, membership_to_pay, int(form.cleaned_data["payment_method"])
        )

        if payment_success:

            return _refresh_edit_member(
                request,
                club,
                system_number,
                payment_message,
                show_history=True,
            )

        else:
            message = payment_message

    else:

        form = MembershipPaymentForm(
            club=club,
            registered=(member_details.user_type == f"{GLOBAL_TITLE} User"),
        )

    return render(
        request,
        "organisations/club_menu/members/club_admin_edit_member_payment_htmx.html",
        {
            "club": club,
            "system_number": system_number,
            "membership": membership_to_pay,
            "form": form,
            "message": message,
        },
    )


@check_club_menu_access(check_members=True)
def club_admin_edit_member_extend_htmx(request, club):
    """
    Handle the extend membership sub-view
    """

    system_number = request.POST.get("system_number", None)
    if not system_number:
        return _refresh_edit_member(
            request,
            club,
            system_number,
            "Error - system number not specified",
        )

    member_details = get_member_details(club, system_number)

    permitted_action, message = can_perform_action("extend", member_details)
    if not permitted_action:
        # should not be here - redirect with an error message
        return _refresh_edit_member(
            request,
            club,
            system_number,
            message,
        )

    if "save" in request.POST:

        form = MembershipExtendForm(
            request.POST,
            club=club,
            registered=(member_details.user_type == f"{GLOBAL_TITLE} User"),
        )
        if form.is_valid():

            success, message = renew_membership(
                club,
                system_number,
                form.cleaned_data["new_end_date"],
                form.cleaned_data["fee"],
                form.cleaned_data["due_date"],
                payment_method_id=int(form.cleaned_data["payment_method"]),
                process_payment=True,
                requester=request.user,
            )

            if success:
                return _refresh_edit_member(
                    request,
                    club,
                    system_number,
                    message if message else "Membership extended",
                )

    else:
        message = None
        default_due_date = club.next_renewal_date + timedelta(
            days=member_details.latest_membership.membership_type.grace_period_days
        )

        initial_data = {
            "new_end_date": club.next_end_date.strftime("%Y-%m-%d"),
            "fee": member_details.latest_membership.membership_type.annual_fee,
            "due_date": default_due_date.strftime("%Y-%m-%d"),
            "payment_method": -1,
        }
        form = MembershipExtendForm(
            initial=initial_data,
            club=club,
            registered=(member_details.user_type == f"{GLOBAL_TITLE} User"),
        )

    return render(
        request,
        "organisations/club_menu/members/club_admin_edit_member_extend_htmx.html",
        {
            "club": club,
            "system_number": system_number,
            "form": form,
            "message": message,
        },
    )


@check_club_menu_access(check_members=True)
def club_admin_add_member_htmx(request, club):
    """Add a member to the club

    Handles registered users, unregistered users and MPC imports

    Renders the wrapper HTML that triggers an HTMX load of the shared
    club_admin_edit_member_change_htmx.html

    System number of new member is passed in the POST
    """

    system_number = request.POST.get("system_number")
    member_admin = rbac_user_has_role(request.user, f"orgs.members.{club.id}.edit")
    has_errors = _check_member_errors(club)

    return render(
        request,
        "organisations/club_menu/members/club_admin_add_member_htmx.html",
        {
            "club": club,
            "system_number": system_number,
            "member_admin": member_admin,
            "has_errors": has_errors,
            "full_membership_mgmt": club.full_club_admin,
        },
    )


@check_club_menu_access(check_members=True)
def club_admin_add_member_detail_htmx(request, club):
    """End point for handling the shared club_admin_edit_member_change_htmx.html
    when adding a new club member"""

    # JPG Detail
    print("club_admin_add_member_detail_htmx")

    system_number = request.POST.get("system_number")

    user = User.objects.filter(
        system_number=system_number,
    ).last()

    mpc_details = None
    if user:
        user_type = "REG"
    else:
        user = UnregisteredUser.objects.filter(
            system_number=system_number,
        ).last()
        if user:
            user_type = "UNR"
        else:
            user_type = "MPC"
            mpc_details = get_mpc_details(club, system_number)

    # When the user selects a type in the form the corresponding fee and dates need to be set
    # Note: end_date is not set for types which do not renew (eg Life membership)
    # Note: values are converted to types that JavaScript can ingest

    message = None

    membership_types = MembershipType.objects.filter(organisation=club).all()

    if len(membership_types) == 0:
        # no choices so go back to the add menu
        return add_htmx(
            request, message="You need to create membership types before adding members"
        )

    today = timezone.now().date()
    fees_and_due_dates = {
        f"{mt.id}": {
            "annual_fee": float(mt.annual_fee),
            "due_date": (today + timedelta(mt.grace_period_days)).strftime("%Y-%m-%d"),
            "end_date": " "
            if mt.does_not_renew
            else club.current_end_date.strftime("%Y-%m-%d"),
            "perpetual": "Y" if mt.does_not_renew else "N",
        }
        for mt in membership_types
    }

    welcome_pack = WelcomePack.objects.filter(organisation=club).exists()

    if "save" in request.POST:
        form = MembershipChangeTypeForm(
            request.POST,
            club=club,
            registered=(user_type == "REG"),
        )
        if form.is_valid():

            # JPG debug
            print("=== form is valid")

            if (
                form.cleaned_data["send_welcome_pack"]
                and user_type != "REG"
                and not form.cleaned_data["new_email"]
            ):
                message = "An email address is required to send a welcome pack"
            else:
                membership_type = get_object_or_404(
                    MembershipType, pk=int(form.cleaned_data["membership_type"])
                )

                if user_type == "MPC":
                    # need to create an unregistered user from the MCP data
                    user_type, details = add_un_registered_user_with_mpc_data(
                        system_number, club, request.user
                    )

                success, message = add_member(
                    club,
                    system_number,
                    (user_type == "REG"),
                    membership_type,
                    request.user,
                    fee=form.cleaned_data["fee"],
                    start_date=form.cleaned_data["start_date"],
                    end_date=form.cleaned_data["end_date"],
                    due_date=form.cleaned_data["due_date"],
                    payment_method_id=int(form.cleaned_data["payment_method"]),
                    email=form.cleaned_data["new_email"],
                )

                if success:

                    # JPG debug
                    print("=== post successfull")

                    if form.cleaned_data["send_welcome_pack"]:
                        email = club_email_for_member(club, system_number)
                        if email:
                            resp = _send_welcome_pack(
                                club, user.first_name, email, request.user, False
                            )
                            message = f"{message}. {resp}"

                    return _refresh_edit_member(request, club, system_number, message)

        else:
            message = "Error with the form"

    else:
        initial_data = {
            "membership_type": membership_types.first().id,
            "start_date": today.strftime("%Y-%m-%d"),
            "payment_method": -1,
        }
        if mpc_details and mpc_details["EmailAddress"]:
            initial_data["new_email"] = mpc_details["EmailAddress"]

        form = MembershipChangeTypeForm(
            initial=initial_data,
            club=club,
            registered=(user_type == "REG"),
        )

    return render(
        request,
        "organisations/club_menu/members/club_admin_edit_member_change_htmx.html",
        {
            "club": club,
            "system_number": system_number,
            "form": form,
            "fees_and_dates": f"{fees_and_due_dates}",
            "adding": True,
            "message": message,
            "user": user,
            "welcome_pack": welcome_pack,
            "mpc_details": mpc_details,
        },
    )


@check_club_menu_access(check_members=True)
def club_admin_edit_member_edit_mmt_htmx(request, club):

    system_number = request.POST.get("system_number")
    mmt = get_object_or_404(MemberMembershipType, pk=int(request.POST.get("mmt_id")))

    member_details = get_member_details(club, system_number)

    message = None

    if request.POST.get("save", "NO") == "YES":

        form = MembershipRawEditForm(
            request.POST,
            club=club,
            registered=(member_details.user_type == f"{GLOBAL_TITLE} User"),
        )

        if form.is_valid():

            error = False

            membership_type_id = int(form.cleaned_data["membership_type"])
            new_membership_type = (
                MembershipType.objects.get(pk=membership_type_id)
                if membership_type_id >= 0
                else None
            )

            if (
                new_membership_type
                and not new_membership_type.does_not_renew
                and not form.cleaned_data["end_date"]
            ):
                error = True
                message = (
                    f"Membership type {new_membership_type.name} requires an end date"
                )

            if (
                new_membership_type
                and new_membership_type.does_not_renew
                and form.cleaned_data["end_date"]
            ):
                error = True
                message = f"Membership type {new_membership_type.name} cannot have an end date"

            payment_method_id = int(form.cleaned_data["payment_method"])
            new_payment_method = (
                OrgPaymentMethod.objects.get(pk=payment_method_id)
                if payment_method_id >= 0
                else None
            )

            if (
                not error
                and new_payment_method
                and new_payment_method.payment_method == "Bridge Credits"
                and member_details.user_type != f"{GLOBAL_TITLE} User"
            ):
                error = True
                message = "User must be registered to use Bridge Credits"

            if (
                not error
                and form.cleaned_data["start_date"]
                and form.cleaned_data["end_date"]
                and form.cleaned_data["start_date"] > form.cleaned_data["end_date"]
            ):
                error = True
                message = "End date cannot be before start date"

            if (
                not error
                and form.cleaned_data["auto_pay_date"]
                and form.cleaned_data["auto_pay_date"] <= timezone.now().date()
            ):
                error = True
                message = "Auto pay date must be in the future"

            if not error:

                mmt.membership_type = new_membership_type
                mmt.payment_method = new_payment_method
                mmt.membership_state = form.cleaned_data["membership_state"]
                mmt.start_date = form.cleaned_data["start_date"]
                mmt.end_date = (
                    form.cleaned_data["end_date"]
                    if form.cleaned_data["end_date"]
                    else None
                )
                mmt.paid_until_date = (
                    form.cleaned_data["paid_until_date"]
                    if form.cleaned_data["paid_until_date"]
                    else None
                )
                mmt.due_date = (
                    form.cleaned_data["due_date"]
                    if form.cleaned_data["due_date"]
                    else None
                )
                mmt.paid_date = (
                    form.cleaned_data["paid_date"]
                    if form.cleaned_data["paid_date"]
                    else None
                )
                mmt.auto_pay_date = (
                    form.cleaned_data["auto_pay_date"]
                    if form.cleaned_data["auto_pay_date"]
                    else None
                )
                mmt.fee = form.cleaned_data["fee"]
                mmt.is_paid = form.cleaned_data["is_paid"]
                mmt.last_modified_by = request.user
                mmt.save()

                if mmt == member_details.latest_membership:
                    member_details.membership_status = mmt.membership_state
                    member_details.save()

                return _refresh_edit_member(
                    request, club, system_number, "Changes saved", show_history=True
                )

        else:
            message = "Error on form"

    else:

        initial_data = {
            "membership_type": mmt.membership_type.id if mmt.membership_type else -1,
            "payment_method": mmt.payment_method.id if mmt.payment_method else -1,
        }

        form = MembershipRawEditForm(
            instance=mmt,
            initial=initial_data,
            club=club,
            registered=(member_details.user_type == f"{GLOBAL_TITLE} User"),
        )

    return render(
        request,
        "organisations/club_menu/members/club_admin_edit_member_edit_mmt_htmx.html",
        {
            "club": club,
            "system_number": system_number,
            "mmt": mmt,
            "form": form,
            "message": message,
        },
    )


@check_club_menu_access(check_members=True)
def club_admin_edit_member_delete_mmt_htmx(request, club):

    system_number = request.POST.get("system_number")
    mmt = get_object_or_404(MemberMembershipType, pk=int(request.POST.get("mmt_id")))
    message = ""

    if request.POST.get("delete", "NO") == "YES":

        mmt.delete()

        request.POST = request.POST.copy()
        del request.POST["delete"]
        return _refresh_edit_member(
            request, club, system_number, "Membership record deleted", show_history=True
        )

    refund_warning = (
        mmt.is_paid
        and mmt.payment_method
        and mmt.payment_method.payment_method == "Bridge Credits"
    )

    return render(
        request,
        "organisations/club_menu/members/club_admin_edit_member_delete_mmt_htmx.html",
        {
            "club": club,
            "system_number": system_number,
            "mmt": mmt,
            "refund_warning": refund_warning,
            "message": message,
        },
    )


def get_mpc_details(club, system_number):
    """Return the MCP details for the player, including an email address if the
    player is a home club member. Also includes home club name

    NOTE: This matches home clubs based on club name rather than testing
    Organisaton.org_id against the MPC ClubNumber. This is because the details
    returned by the MPC for a player includes the home club id (not number),
    and it is not clear how to associate the id with a number other than through
    the club name.
    """

    details = user_summary(system_number)

    home_club_details = masterpoint_query_row(f'club/{details["HomeClubID"]}')
    details["HomeClubName"] = home_club_details["ClubName"]

    if club.name == home_club_details["ClubName"]:
        # is a home club member, so get the email address

        matches = search_mpc_users_by_name(details["GivenNames"], details["Surname"])

        mpc_email = None
        for match in matches:
            if match["ABFNumber"] == system_number:
                if "EmailAddress" in match and match["EmailAddress"]:
                    mpc_email = match["EmailAddress"]
                break
        details["EmailAddress"] = mpc_email

    else:
        details["EmailAddress"] = None

    return details


@check_club_menu_access(check_members=True)
def renewals_menu_htmx(request, club):
    """Renewals submenu"""

    message = request.POST.get("message", None)

    return render(
        request,
        "organisations/club_menu/members/renewals_menu_htmx.html",
        {
            "club": club,
            "full_membership_mgmt": club.full_club_admin,
            "message": message,
        },
    )


@check_club_menu_access(check_members=True)
def bulk_renewals_htmx(request, club):
    """Initiate bulk renewals"""

    return HttpResponse("Bulk renewals coming soon")


@check_club_menu_access(check_members=True)
def view_unpaid_htmx(request, club):
    """Initiate bulk renewals"""

    return HttpResponse("Unpaid fees coming soon")


@check_club_menu_access(check_members=True)
def email_unpaid_htmx(request, club):
    """Initiate email batch to unpaid members"""

    return HttpResponse("Email unpaid coming soon")
