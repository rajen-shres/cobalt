import csv
import logging
from itertools import chain

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, HttpRequest
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.utils import timezone

import organisations.views.club_menu_tabs.utils
from accounts.views.admin import invite_to_join
from accounts.views.api import search_for_user_in_cobalt_and_mpc
from accounts.forms import UnregisteredUserForm
from accounts.models import User, UnregisteredUser
from club_sessions.models import SessionEntry
from cobalt.settings import (
    GLOBAL_ORG,
    GLOBAL_TITLE,
    COBALT_HOSTNAME,
    GLOBAL_CURRENCY_SYMBOL,
)
from notifications.models import UnregisteredBlockedEmail, BatchID
from notifications.views.core import (
    custom_sender,
    send_cobalt_email_with_template,
    create_rbac_batch_id,
    club_default_template,
    get_emails_sent_to_address,
)
from organisations.decorators import check_club_menu_access
from organisations.forms import (
    MemberClubEmailForm,
    UserMembershipForm,
    UnregisteredUserAddForm,
    UnregisteredUserMembershipForm,
)
from organisations.models import (
    MemberMembershipType,
    Organisation,
    MemberClubEmail,
    ClubLog,
    MemberClubTag,
    ClubTag,
    MembershipType,
    WelcomePack,
    OrgEmailTemplate,
    MiscPayType,
)
from organisations.views.general import (
    active_email_for_un_reg,
    get_rbac_model_for_state,
)
from payments.models import MemberTransaction, UserPendingPayment
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
    from organisations.views.club_menu_tabs.utils import get_members_for_club

    # get sort options, could be POST or GET
    sort_option = request.GET.get("sort_by")
    if not sort_option:
        sort_option = request.POST.get("sort_by", "first_desc")

    members = get_members_for_club(club, sort_option=sort_option)

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
        },
    )


@check_club_menu_access()
def add_htmx(request, club):
    """Add sub menu"""

    if not MembershipType.objects.filter(organisation=club).exists():
        return HttpResponse(
            "<h4>Your club has no membership types defined. You cannot add a member until you fix this.</h4>"
        )

    total_members = organisations.views.club_menu_tabs.utils.get_member_count(club)

    # Check level of access
    member_admin = rbac_user_has_role(request.user, f"orgs.members.{club.id}.edit")

    has_errors = _check_member_errors(club)

    # Check for unregistered
    members = MemberMembershipType.objects.filter(
        membership_type__organisation=club
    ).values("system_number")
    has_unregistered = UnregisteredUser.objects.filter(
        system_number__in=members
    ).exists()

    return render(
        request,
        "organisations/club_menu/members/add_menu_htmx.html",
        {
            "club": club,
            "total_members": total_members,
            "member_admin": member_admin,
            "has_errors": has_errors,
            "has_unregistered": has_unregistered,
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
        },
    )


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

    email_address = active_email_for_un_reg(un_reg, club)

    # Get recent emails if allowed
    # if rbac_user_has_role(
    #     request.user, f"notifications.orgcomms.{club.id}.edit"
    # ) or rbac_user_has_role(request.user, "orgs.admin.edit"):
    #     if email_address:
    #         emails = PostOfficeEmail.objects.filter(to=[email_address]).order_by("-pk")[
    #             :20
    #         ]
    #     else:
    #         emails = None
    # else:
    #     emails = None

    # JPG cleanup

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
        print(f"++++++ _send_welcome_pack url={use_template.banner.url}")

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

    member_list = (
        MemberMembershipType.objects.filter(system_number__in=user_list_system_numbers)
        .filter(membership_type__organisation=club)
        .values_list("system_number", flat=True)
    )

    for user in user_list:
        if user["system_number"] in member_list:
            user["source"] = "member"

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


@check_club_menu_access(check_members=True)
def edit_member_htmx(request, club, message=""):
    """Edit a club member manually"""

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
        },
    )


def _get_misc_payment_vars(member, club):
    """get variables relating to this members misc payments for this club"""

    # Get recent misc payments
    recent_payments = MemberTransaction.objects.filter(
        member=member, organisation=club
    ).order_by("-created_date")[:10]

    # get this orgs miscellaneous payment types
    misc_payment_types = MiscPayType.objects.filter(organisation=club)

    return recent_payments, misc_payment_types


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
        {"has_errors": has_errors, "member_admin": member_admin, "club": club},
    )


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


@check_club_menu_access(check_members=True)
def member_search_tab_htmx(request, club):
    """member search tab"""

    member_admin = rbac_user_has_role(request.user, f"orgs.members.{club.id}.edit")

    return render(
        request,
        "organisations/club_menu/members/member_search_tab_htmx.html",
        {"member_admin": member_admin, "club": club},
    )


@check_club_menu_access()
def member_search_tab_name_htmx(request, club):
    """Search function for searching for a member by name"""

    first_name_search = request.POST.get("member_first_name_search")
    last_name_search = request.POST.get("member_last_name_search")

    # if there is nothing to search for, don't search
    if not first_name_search and not last_name_search:
        return HttpResponse()

    member_list = MemberMembershipType.objects.filter(
        membership_type__organisation=club
    ).values_list("system_number", flat=True)

    # Users
    users = User.objects.filter(system_number__in=member_list)

    if first_name_search:
        users = users.filter(first_name__istartswith=first_name_search)

    if last_name_search:
        users = users.filter(last_name__istartswith=last_name_search)

    # Unregistered
    un_regs = UnregisteredUser.objects.filter(system_number__in=member_list)

    if first_name_search:
        un_regs = un_regs.filter(first_name__istartswith=first_name_search)

    if last_name_search:
        un_regs = un_regs.filter(last_name__istartswith=last_name_search)

    user_list = list(chain(users, un_regs))

    return render(
        request,
        "organisations/club_menu/members/member_search_tab_name_htmx.html",
        {"user_list": user_list, "club": club},
    )


@check_club_menu_access()
def member_search_tab_email_htmx(request, club):
    """Search function for searching for a member by email"""

    email_search = request.POST.get("member_email_search")

    # if there is nothing to search for, don't search
    if not email_search:
        return HttpResponse()

    # Unregistered Only
    member_club_system_number_list = (
        MemberClubEmail.objects.filter(email__icontains=email_search)
        .filter(organisation=club)
        .values("system_number")
    )
    un_regs = UnregisteredUser.objects.filter(
        system_number__in=member_club_system_number_list
    )

    return render(
        request,
        "organisations/club_menu/members/member_search_tab_name_htmx.html",
        {"user_list": un_regs, "club": club},
    )


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
            club_email = MemberClubEmail.objects.filter(
                system_number=member.system_number, organisation=club
            ).first()
            if club_email and invite_to_join(
                member, club_email.email, request.user, club
            ):
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
