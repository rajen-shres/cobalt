from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from club_sessions.models import SessionType, SessionTypePaymentMethod
from cobalt.settings import GLOBAL_MPSERVER
from organisations.decorators import check_club_menu_access
from organisations.forms import (
    OrgForm,
    OrgDatesForm,
    MembershipTypeForm,
    VenueForm,
    PaymentTypeForm,
)
from organisations.models import ClubLog, MembershipType, MemberMembershipType, OrgVenue
from organisations.views.admin import get_secretary_from_org_form
from organisations.views.club_menu_tabs.utils import _user_is_uber_admin
from organisations.views.general import compare_form_with_mpc
from payments.models import OrgPaymentMethod
from utils.views import masterpoint_query


@check_club_menu_access()
def basic_htmx(request, club):
    """build the settings tab in club menu for editing basic details"""

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


@check_club_menu_access()
def basic_reload_htmx(request, club):
    """Reload data from MPC and return the settings basic tab"""

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

    return basic_htmx(request)


@check_club_menu_access()
def logs_htmx(request, club):
    """Shows the log events"""

    log_events = ClubLog.objects.filter(organisation=club).order_by("-pk")

    return render(
        request,
        "organisations/club_menu/settings/logs_htmx.html",
        {"log_events": log_events},
    )


@check_club_menu_access()
def general_htmx(request, club):
    """build the settings tab in club menu for editing general details"""

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

    venues = OrgVenue.objects.filter(organisation=club)

    return render(
        request,
        "organisations/club_menu/settings/general_htmx.html",
        {
            "club": club,
            "form": form,
            "message": message,
            "venues": venues,
        },
    )


@check_club_menu_access()
def membership_htmx(request, club):
    """build the settings tab in club menu for editing membership types"""

    membership_types = MembershipType.objects.filter(organisation=club)

    return render(
        request,
        "organisations/club_menu/settings/membership_htmx.html",
        {
            "club": club,
            "membership_types": membership_types,
        },
    )


@check_club_menu_access()
def club_menu_tab_settings_membership_edit_htmx(request, club):
    """Part of the settings tab for membership types to allow user to edit the membership type

    When a membership type is clicked on, this code is run and returns a form to edit the
    details.
    """

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


@check_club_menu_access()
def club_menu_tab_settings_membership_add_htmx(request, club):
    """Part of the settings tab for membership types to allow user to add a membership type"""

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
        return membership_htmx(request, club)

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


@check_club_menu_access()
def club_menu_tab_settings_membership_delete_htmx(request, club):
    """Part of the settings tab for membership types to allow user to delete a membership type"""

    # Get membership type id
    membership_type_id = request.POST.get("membership_type_id")
    membership_type = get_object_or_404(MembershipType, pk=membership_type_id)

    # Check for active members in this membership type
    if (
        MemberMembershipType.objects.active()
        .filter(membership_type=membership_type)
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

    return membership_htmx(request, club)


@check_club_menu_access()
def club_menu_tab_settings_sessions_htmx(request, club):
    """Show club sessions details"""

    session_types = SessionType.objects.filter(organisation=club)

    return render(
        request,
        "organisations/club_menu/settings/sessions_htmx.html",
        {"session_types": session_types},
    )


@check_club_menu_access()
def club_menu_tab_settings_session_edit_htmx(request, club):
    """Part of the settings tab for session types to allow user to edit the session type

    When a session type is clicked on, this code is run and returns a form to edit the
    details.
    """

    session_type = get_object_or_404(
        SessionType, pk=request.POST.get("session_type_id")
    )

    # This is a POST even the first time so look for "save" to see if this really is a form submit
    # real_post = "save" in request.POST

    # if not real_post:
    #     form = MembershipTypeForm(instance=membership_type)
    # else:
    #     form = MembershipTypeForm(request.POST, instance=membership_type)
    #
    # message = ""
    #
    # if form.is_valid():
    #     updated = form.save(commit=False)
    #     updated.last_modified_by = request.user
    #     updated.save()
    #     ClubLog(
    #         organisation=club,
    #         actor=request.user,
    #         action=f"Updated membership type: {updated}",
    #     ).save()
    #     message = "Membership Type Updated"

    return render(
        request,
        "organisations/club_menu/settings/session_edit_htmx.html",
        {"session_type": session_type},
    )


@check_club_menu_access()
def club_menu_tab_settings_payment_htmx(request, club):
    """Show club payment types"""

    if "add" in request.POST:
        form = PaymentTypeForm(request.POST, club=club)

        if form.is_valid():
            payment_type = OrgPaymentMethod(
                organisation=club, payment_method=form.cleaned_data["payment_name"]
            )
            payment_type.save()

            ClubLog(
                organisation=club,
                actor=request.user,
                action=f"Added payment type: {payment_type.payment_method}",
            ).save()

            # reset form
            form = PaymentTypeForm(club=club)
    else:
        form = PaymentTypeForm(club=club)

    payment_methods = OrgPaymentMethod.objects.filter(organisation=club).order_by(
        "-active"
    )

    return render(
        request,
        "organisations/club_menu/settings/payment_htmx.html",
        {"payment_methods": payment_methods, "club": club, "form": form},
    )


@check_club_menu_access()
def club_menu_tab_settings_venues_htmx(request, club):
    """Show club venues"""

    if "add" in request.POST:
        form = VenueForm(request.POST, club=club)

        if form.is_valid():
            venue = OrgVenue(organisation=club, venue=form.cleaned_data["venue_name"])
            venue.save()

            ClubLog(
                organisation=club,
                actor=request.user,
                action=f"Added venue: {venue.venue}",
            ).save()

            # reset form
            form = VenueForm(club=club)
    else:
        form = VenueForm(club=club)

    venues = OrgVenue.objects.filter(organisation=club)

    # Add on htmx data for venues
    for venue in venues:
        venue.hx_post = reverse(
            "organisations:club_menu_tab_settings_delete_venue_htmx"
        )
        venue.hx_vars = f"club_id:{club.id},venue_id:{venue.id}"

    return render(
        request,
        "organisations/club_menu/settings/venues_htmx.html",
        {"venues": venues, "form": form, "club": club},
    )


@check_club_menu_access()
def club_menu_tab_settings_delete_venue_htmx(request, club):
    """Delete a venue"""

    venue = get_object_or_404(OrgVenue, pk=request.POST.get("venue_id"))

    ClubLog(
        organisation=club, actor=request.user, action=f"Deleted venue: {venue.venue}"
    ).save()

    venue.delete()

    return club_menu_tab_settings_venues_htmx(request)


@check_club_menu_access()
def club_menu_tab_settings_toggle_payment_type_htmx(request, club):
    """toggle a payment type on or off"""

    payment_type = get_object_or_404(
        OrgPaymentMethod, pk=request.POST.get("payment_type_id")
    )

    if payment_type.active:
        ClubLog(
            organisation=club,
            actor=request.user,
            action=f"Disabled payment method: {payment_type.payment_method}",
        ).save()
        payment_type.active = False
    else:
        ClubLog(
            organisation=club,
            actor=request.user,
            action=f"Activated payment method: {payment_type.payment_method}",
        ).save()
        payment_type.active = True
    payment_type.save()

    return club_menu_tab_settings_payment_htmx(request)
