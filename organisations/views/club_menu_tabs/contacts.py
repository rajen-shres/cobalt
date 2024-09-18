import csv
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, HttpRequest
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    NextInternalSystemNumber,
    UnregisteredUser,
)
from accounts.views.api import search_for_user_in_cobalt_and_mpc
from cobalt.settings import (
    GLOBAL_ORG,
    GLOBAL_TITLE,
)
from organisations.club_admin_core import (
    add_contact_with_system_number,
    club_email_for_member,
    convert_contact_to_member,
    delete_contact,
    get_club_contacts,
    get_club_contact_list,
    get_club_member_list,
    get_contact_details,
    get_contact_system_numbers,
    get_membership_details_for_club,
    get_member_log,
    get_member_system_numbers,
    get_valid_activities,
    log_member_change,
)
from organisations.decorators import check_club_menu_access
from organisations.forms import (
    ContactAddForm,
    MemberClubDetailsForm,
    MembershipChangeTypeForm,
)
from organisations.views.club_menu_tabs.members import (
    _refresh_edit_member,
    _refresh_member_list,
    _send_welcome_pack,
)
from organisations.views.general import (
    get_rbac_model_for_state,
)
from organisations.models import (
    MemberClubDetails,
    MemberClubTag,
    MembershipType,
    Organisation,
    WelcomePack,
)
from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden
from utils.utils import cobalt_paginator


def _refresh_edit_contact(request, club, system_number, message):
    """Refreshes the edit contact view from within the view
    ie. call as the result of an htmx end point to refresh the view
    """

    return render(
        request,
        "organisations/club_menu/contacts/club_admin_edit_contact_refresh_htmx.html",
        {
            "club_id": club.id,
            "system_number": system_number,
            "message": message,
        },
    )


def _refresh_contact_list(request, club, message):
    """Refreshes the contact list view from within the view
    ie. call as the result of an htmx end point to refresh the view
    """

    return render(
        request,
        "organisations/club_menu/contacts/club_admin_contact_list_refresh_htmx.html",
        {
            "club_id": club.id,
            "message": message,
        },
    )


@check_club_menu_access()
def list_htmx(request, club, message=None):
    """Build the contacts tab in club menu"""

    if not message and "message" in request.POST:
        message = request.POST["message"]

    DEFAULT_SORT = "last_desc"

    # get sort options
    sort_option = request.GET.get("sort_by")
    if not sort_option:
        sort_option = request.POST.get("sort_by")
        if not sort_option:
            sort_option = DEFAULT_SORT

    contacts = get_club_contacts(
        club,
        sort_option=sort_option,
    )

    # pagination and params
    things = cobalt_paginator(request, contacts)
    searchparams = f"sort_by={sort_option}&"

    total_contacts = len(contacts)

    # Check level of access
    member_admin = rbac_user_has_role(request.user, f"orgs.members.{club.id}.edit")

    hx_post = reverse("organisations:club_menu_tab_contacts_htmx")

    return render(
        request,
        "organisations/club_menu/contacts/list_htmx.html",
        {
            "club": club,
            "things": things,
            "total_contacts": total_contacts,
            "message": message,
            "member_admin": member_admin,
            "hx_post": hx_post,
            "searchparams": searchparams,
            "sort_option": sort_option,
        },
    )


@check_club_menu_access()
def add_htmx(request, club, message=None):
    """Add a contact through various means"""

    return render(
        request,
        "organisations/club_menu/contacts/add_htmx.html",
        {
            "club": club,
        },
    )


@check_club_menu_access()
def edit_htmx(request, club, message=None):
    """Edit a contact"""

    system_number = request.POST.get("system_number", None)
    message = request.POST.get("message", None)
    saving = request.POST.get("save", "NO") == "YES"
    editing = request.POST.get("edit", "NO") == "YES"

    if not system_number:
        # JPG to do - this call will not work. perhaps raise an exception instead
        return list_htmx(request, message="System number required")

    contact_details = get_contact_details(club, system_number)

    # get the members log history
    log_history_full = get_member_log(club, system_number)
    log_history = cobalt_paginator(
        request, log_history_full, items_per_page=5, page_no=request.POST.get("page", 1)
    )

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

    if saving:
        form = MemberClubDetailsForm(request.POST, instance=contact_details)
        if form.is_valid():
            form.save()
            message = "Updates saved"
        else:
            message = "Error saving updates"
            editing = True

    else:
        form = MemberClubDetailsForm(instance=contact_details)

    # Note: member_admin is used in conditioning the contact nav area.
    # The user has this access if they have got this far.

    return render(
        request,
        "organisations/club_menu/contacts/edit_htmx.html",
        {
            "club": club,
            "contact_details": contact_details,
            "form": form,
            "message": message,
            "member_admin": True,
            "edit_details": editing,
            "log_history": log_history,
            "system_number": contact_details.system_number,
            "permitted_activities": get_valid_activities(contact_details),
        },
    )


@check_club_menu_access()
def tags_htmx(request, club):

    system_number = request.POST.get("system_number", None)
    contact_details = get_contact_details(club, system_number)

    return render(
        request,
        "organisations/club_menu/contacts/tags_htmx.html",
        {
            "club": club,
            "contact_details": contact_details,
        },
    )


@check_club_menu_access()
def emails_htmx(request, club):

    system_number = request.POST.get("system_number", None)
    contact_details = get_contact_details(club, system_number)

    return render(
        request,
        "organisations/club_menu/contacts/emails_htmx.html",
        {
            "club": club,
            "contact_details": contact_details,
        },
    )


@check_club_menu_access()
def delete_htmx(request, club):

    success, message = delete_contact(club, request.POST["system_number"])

    return _refresh_contact_list(
        request,
        club,
        message,
    )


@check_club_menu_access()
def convert_select_system_number_htmx(request, club):
    """
    Search function for converting a member (registered, unregistered or from MPC)
    """

    system_number = request.POST.get("system_number", None)
    contact_details = get_contact_details(club, system_number)
    last_name_only = request.POST.get("last_name_only", "NO") == "YES"
    caller = request.POST.get("caller", "contacts")

    if not contact_details.internal:
        # not an internal system number, so just go to the next stage

        request.POST = request.POST.copy()
        request.POST["new_system_number"] = system_number
        return convert_htmx(request)

    user_list, is_more = search_for_user_in_cobalt_and_mpc(
        contact_details.first_name,
        contact_details.last_name,
        last_name_only=last_name_only,
    )

    # Now highlight users who are already club members
    user_list_system_numbers = [user["system_number"] for user in user_list]

    member_list = get_member_system_numbers(club, target_list=user_list_system_numbers)
    contact_list = get_contact_system_numbers(
        club, target_list=user_list_system_numbers
    )

    for user in user_list:
        if user["system_number"] in member_list:
            user["source"] = "member"
        elif user["system_number"] in contact_list:
            user["source"] = "contact"

    return render(
        request,
        "organisations/club_menu/contacts/convert_system_number_select_htmx.html",
        {
            "club": club,
            "contact_details": contact_details,
            "user_list": user_list,
            "is_more": is_more,
            "caller": caller,
        },
    )


@check_club_menu_access()
def convert_htmx(request, club):
    """Convert a contact to a member.

    Requires the user to input the membership details and a real
    ABF number if the contact has an internal one.

    Based on members.py club_admin_edit_member_change_htmx()
    and shares the template

    Args:
        request (HttpRequest): the request
        club_id (int): the club's Organisation id
        system_number (int): the contacts's system number

    Returns:
        HttpResponse: the response
    """

    message = None
    today = timezone.now().date()

    system_number = request.POST.get("system_number")
    new_system_number = request.POST.get("new_system_number")
    caller = request.POST.get("caller", "contacts")

    welcome_pack = WelcomePack.objects.filter(organisation=club).exists()

    contact_details = get_contact_details(club, system_number)

    membership_choices, fees_and_due_dates = get_membership_details_for_club(club)

    if len(membership_choices) == 0:
        # no choices so go back to the main view

        return _refresh_edit_contact(
            request,
            club,
            system_number,
            "Unable to convert, no membership types available",
        )

    if request.POST.get("save", "NO") == "YES":
        form = MembershipChangeTypeForm(
            request.POST,
            club=club,
            registered=(contact_details.user_type == f"{GLOBAL_TITLE} User"),
        )
        if form.is_valid():

            if (
                form.cleaned_data["send_welcome_pack"]
                and not contact_details.email
                and not form.cleaned_data["new_email"]
            ):
                message = "An email address is required to send a welcome pack"
            else:

                membership_type = get_object_or_404(
                    MembershipType, pk=int(form.cleaned_data["membership_type"])
                )

                new_system_number = form.cleaned_data["new_system_number"]
                if not new_system_number:
                    # system number is not changing
                    new_system_number = contact_details.system_number

                # post logic
                success, message = convert_contact_to_member(
                    club,
                    contact_details.system_number,
                    new_system_number,
                    membership_type,
                    request.user,
                    fee=form.cleaned_data["fee"],
                    start_date=form.cleaned_data["start_date"],
                    end_date=form.cleaned_data["end_date"],
                    due_date=form.cleaned_data["due_date"],
                    payment_method_id=int(form.cleaned_data["payment_method"]),
                )

                if success:

                    if form.cleaned_data["send_welcome_pack"]:
                        email = club_email_for_member(club, system_number)
                        if email:
                            resp = _send_welcome_pack(
                                club,
                                contact_details.first_name,
                                email,
                                request.user,
                                False,
                            )
                            if resp:
                                if message:
                                    message = f"{message}. {resp}"
                                else:
                                    message = f"Contact converted to member. {resp}"

                    if caller == "contacts":
                        return _refresh_contact_list(
                            request,
                            club,
                            message if message else "Contact converted to member",
                        )
                    else:
                        return _refresh_member_list(
                            request,
                            club,
                            message if message else "Contact converted to member",
                        )

        else:
            # Invalid form
            message = "Please fix issues with the form"

    else:
        initial_data = {
            "membership_type": membership_choices[0][0],
            "start_date": today.strftime("%Y-%m-%d"),
            "new_system_number": new_system_number,
            "payment_method": -1,
            "send_welcome_pack": welcome_pack,
        }
        form = MembershipChangeTypeForm(
            initial=initial_data,
            club=club,
            registered=(contact_details.user_type == f"{GLOBAL_TITLE} User"),
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
            "converting": True,
            "internal": contact_details.internal,
            "welcome_pack": welcome_pack,
            "caller": caller,
        },
    )


@check_club_menu_access()
def add_contact_manual_htmx(request, club):
    """Add a new contact manually

    Handles two scenarios:
    1.  Picking an existing member from search results (could be an existing user,
        an existing unregistered user or an MPC member who is not on Cobalt at all.
    2.  Entering first and last name, with no system number
    """

    message = None

    if "save" in request.POST:

        if request.POST.get("save") == "INTERNAL":
            # No ABF number provided, so use the form name details and
            # create an internal system number

            form = ContactAddForm(request.POST)
            if form.is_valid():

                with transaction.atomic():

                    # create a new unregistered user with an internal system number
                    unreg_user = UnregisteredUser()
                    unreg_user.system_number = NextInternalSystemNumber.next_available()
                    unreg_user.first_name = form.cleaned_data["first_name"]
                    unreg_user.last_name = form.cleaned_data["last_name"]
                    unreg_user.origin = "Manual"
                    unreg_user.internal_system_number = True
                    unreg_user.added_by_club = club
                    unreg_user.last_updated_by = request.user
                    unreg_user.save()

                    # create a new member details record
                    add_contact_with_system_number(
                        club,
                        unreg_user.system_number,
                    )

                    # log it
                    log_member_change(
                        club,
                        unreg_user.system_number,
                        request.user,
                        "Contact created (manual)",
                    )

                # redirect to member edit
                return _refresh_edit_contact(
                    request,
                    club,
                    unreg_user.system_number,
                    "Contact created",
                )
        else:
            # a search result has been selected so use that

            system_number = request.POST.get("system_number", None)

            if system_number:

                source = request.POST.get("source", None)

                if source == "mpc":
                    # need to create a new unregistered user
                    unreg_user = UnregisteredUser()
                    unreg_user.system_number = system_number
                    unreg_user.first_name = request.POST.get("first_name")
                    unreg_user.last_name = request.POST.get("last_name")
                    unreg_user.origin = "MCP"
                    unreg_user.added_by_club = club
                    unreg_user.last_updated_by = request.user
                    unreg_user.save()

                add_contact_with_system_number(
                    club,
                    system_number,
                )

                # log it
                log_member_change(
                    club,
                    system_number,
                    request.user,
                    f"Contact added ({source})",
                )

                # redirect to member edit
                return _refresh_edit_contact(
                    request,
                    club,
                    system_number,
                    "Contact added",
                )

            else:
                form = ContactAddForm(request.POST)
                message = "Invalid selection"

    else:
        form = ContactAddForm()

    return render(
        request,
        "organisations/club_menu/contacts/add_individual_contact_system_htmx.html",
        {
            "club": club,
            "form": form,
            "message": message,
        },
    )


@login_required()
def add_search_htmx(request):

    first_name_search = request.POST.get("first_name")
    last_name_search = request.POST.get("last_name")
    club_id = request.POST.get("club_id")

    # if there is nothing to search for, don't search
    if not first_name_search and not last_name_search:
        return HttpResponse()

    user_list, is_more = search_for_user_in_cobalt_and_mpc(
        first_name_search, last_name_search
    )

    # JPG clean-up, not used
    # Now highlight users who are already club members or contacts
    # user_list_system_numbers = [user["system_number"] for user in user_list]

    club = get_object_or_404(Organisation, pk=club_id)

    member_list = get_club_member_list(club)
    contact_list = get_club_contact_list(club)

    for user in user_list:
        if user["system_number"] in member_list:
            user["source"] = "member"
        elif user["system_number"] in contact_list:
            user["source"] = "contact"

    return render(
        request,
        "organisations/club_menu/contacts/contact_search_results_htmx.html",
        {
            "user_list": user_list,
            "is_more": is_more,
            "club_id": club_id,
        },
    )


@check_club_menu_access()
def add_individual_internal_htmx(request, club):
    """Get the name for a new contact (without a system number), create a new contact
    and redirect to the edit contact view for this new contact"""

    if "save" in request.POST:
        form = ContactAddForm(request.POST)
        if form.is_valid():

            with transaction.atomic():

                # create a new unregistered user with an internal system number
                unreg_user = UnregisteredUser()
                unreg_user.system_number = NextInternalSystemNumber.next_available()
                unreg_user.first_name = form.cleaned_data["first_name"]
                unreg_user.last_name = form.cleaned_data["last_name"]
                unreg_user.origin = "Manual"
                unreg_user.internal_system_number = True
                unreg_user.added_by_club = club
                unreg_user.last_updated_by = request.user
                unreg_user.save()

                # create a new member details record
                contact_details = MemberClubDetails()
                contact_details.club = club
                contact_details.system_number = unreg_user.system_number
                contact_details.membership_status = (
                    MemberClubDetails.MEMBERSHIP_STATUS_CONTACT
                )
                contact_details.save()

            # redirect to member edit
            return _refresh_edit_contact(
                request,
                club,
                unreg_user.system_number,
                "Contact created",
            )

    else:
        form = ContactAddForm()

    return render(
        request,
        "organisations/club_menu/contacts/add_individual_contact_internal_htmx.html",
        {"club": club, "form": form},
    )


# JPG not required - in import_data.py
@check_club_menu_access()
def upload_csv_htmx(request, club):

    return HttpResponse("Contact CSV upload coming soon")


@check_club_menu_access()
def reports_htmx(request, club):
    """Reports sub menu"""

    # Check level of access
    member_admin = rbac_user_has_role(request.user, f"orgs.members.{club.id}.edit")

    return render(
        request,
        "organisations/club_menu/contacts/reports_htmx.html",
        {
            "club": club,
            "member_admin": member_admin,
        },
    )


@login_required()
def club_admin_report_all_csv(request, club_id):
    """CSV of all contacts. We can't use the decorator as I can't get HTMX to treat this as a CSV"""

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
    club_contacts = get_club_contacts(club)
    club_contacts_list = [contact.system_number for contact in club_contacts]

    # Get tags and turn into dictionary
    tags = MemberClubTag.objects.filter(
        system_number__in=club_contacts_list, club_tag__organisation=club
    )
    tags_dict = {}
    for tag in tags:
        if tag.system_number not in tags_dict:
            tags_dict[tag.system_number] = []
        tags_dict[tag.system_number].append(tag.club_tag.tag_name)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="contacts.csv"'

    now = timezone.now()

    writer = csv.writer(response)
    writer.writerow([club.name, f"Downloaded by {request.user.full_name}", now])
    writer.writerow(
        [
            f"{GLOBAL_ORG} Number",
            "First Name",
            "Last Name",
            f"{GLOBAL_TITLE} User Type",
            "Email",
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

    for contact in club_contacts:
        contact_tags = tags_dict.get(contact.system_number, "")

        writer.writerow(
            [
                contact.system_number,
                contact.first_name,
                contact.last_name,
                contact.user_type,
                contact.email,
                contact.address1,
                contact.address2,
                contact.state,
                contact.postcode,
                contact.mobile,
                contact.other_phone,
                contact.dob,
                contact.emergency_contact,
                contact_tags,
                contact.notes,
            ]
        )

    return response
