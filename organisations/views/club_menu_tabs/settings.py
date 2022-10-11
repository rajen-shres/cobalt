import random
import string

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from club_sessions.views.admin import (
    add_club_session,
    add_payment_method_session_type_combos,
    turn_off_payment_type,
)
from club_sessions.models import (
    SessionType,
    SessionTypePaymentMethod,
    SessionTypePaymentMethodMembership,
)
from cobalt.settings import GLOBAL_MPSERVER, COBALT_HOSTNAME
from organisations.decorators import check_club_menu_access
from organisations.forms import (
    OrgForm,
    OrgDatesForm,
    MembershipTypeForm,
    VenueForm,
    PaymentTypeForm,
    TagForm,
    TemplateBannerForm,
    WelcomePackForm,
    TemplateForm,
    OrgDefaultSecondaryPaymentMethod,
    MinimumBalanceAfterSettlementForm,
)
from organisations.models import (
    ClubLog,
    MembershipType,
    MemberMembershipType,
    OrgVenue,
    MiscPayType,
    ClubTag,
    MemberClubTag,
    OrgEmailTemplate,
    WelcomePack,
)
from organisations.views.admin import get_secretary_from_org_form
from organisations.views.club_menu_tabs.members import _send_welcome_pack
from organisations.views.club_menu_tabs.utils import (
    _user_is_uber_admin,
    get_club_members_from_system_number_list,
    get_members_for_club,
)
from organisations.views.general import compare_form_with_mpc
from payments.models import OrgPaymentMethod
from rbac.core import rbac_user_has_role
from utils.views import masterpoint_query


@check_club_menu_access()
def basic_htmx(request, club):
    """build the settings tab in club menu for editing basic details"""

    message = ""

    # The form handles the RBAC checks

    # Check if this user is state or global admin - then they can change the State or org_id
    uber_admin = _user_is_uber_admin(club, request.user)

    # This is a POST even the first time so look for "save" to see if this really is a form submit
    real_post = "Save" in request.POST

    if not real_post:
        org_form = OrgForm(user=request.user, instance=club)
    else:

        org_form = OrgForm(request.POST, user=request.user, instance=club)

        # Check for edit access
        if not uber_admin and not rbac_user_has_role(
            request.user, f"orgs.org.{club.id}.edit"
        ):
            message = "You do not have access to change this"

        elif org_form.is_valid():
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

    log_events = ClubLog.objects.filter(organisation=club).order_by("-action_date")

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

        if not rbac_user_has_role(request.user, f"orgs.org.{club.id}.edit"):
            message = "You do not have access to edit this"

        elif form.is_valid():
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

    membership_types = MembershipType.objects.filter(organisation=club).order_by("pk")

    # Add in number of members
    for membership_type in membership_types:
        membership_type.get_member_count = MemberMembershipType.objects.filter(
            membership_type=membership_type
        ).count()

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

    form = (
        MembershipTypeForm(request.POST, instance=membership_type)
        if real_post
        else MembershipTypeForm(instance=membership_type)
    )

    message = ""

    if not rbac_user_has_role(request.user, f"orgs.org.{club.id}.edit"):
        message = "You do not have access to edit this"
    elif form.is_valid():
        updated = form.save(commit=False)
        updated.last_modified_by = request.user
        updated.save()
        ClubLog(
            organisation=club,
            actor=request.user,
            action=f"Updated membership type: {updated}",
        ).save()
        message = "Membership Type Updated"

        if "name" in form.changed_data:
            message += (
                ". Click on Static Data -> Membership Types above, "
                "to refresh the list and see the name change."
            )

    # Don't show option to set as default if there is already a default, unless we are it
    if (
        MembershipType.objects.filter(organisation=club, is_default=True)
        .exclude(pk=membership_type.id)
        .exists()
    ):
        # This throws a non-fatal error but actually works!
        del form.fields["is_default"]

    # Don't allow delete for last membership type
    allow_delete = MembershipType.objects.filter(organisation=club).count() > 1

    return render(
        request,
        "organisations/club_menu/settings/membership_edit_htmx.html",
        {
            "club": club,
            "membership_type": membership_type,
            "form": form,
            "message": message,
            "allow_delete": allow_delete,
        },
    )


@check_club_menu_access(check_members=True)
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

        # Update any sessions with the new payment type
        add_payment_method_session_type_combos(club)

        return membership_htmx(request)
    else:
        print(form.errors)

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


@check_club_menu_access(check_members=True)
def club_menu_tab_settings_membership_delete_htmx(request, club):
    """Part of the settings tab for membership types to allow user to delete a membership type"""

    # Get membership type id
    membership_type_id = request.POST.get("membership_type_id")
    membership_type = get_object_or_404(MembershipType, pk=membership_type_id)

    # Check for active members in this membership type
    if MemberMembershipType.objects.filter(membership_type=membership_type).exists():
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

    membership_type.delete()
    # Delete any invalid session payment records
    turn_off_payment_type(club)

    return membership_htmx(request)


@check_club_menu_access()
def club_menu_tab_settings_sessions_htmx(request, club):
    """Show club sessions details"""

    session_types = SessionType.objects.filter(organisation=club)

    return render(
        request,
        "organisations/club_menu/settings/sessions_htmx.html",
        {"session_types": session_types, "club": club},
    )


@check_club_menu_access()
def club_menu_tab_settings_session_edit_htmx(request, club, check_org_edit=True):
    """Part of the settings tab for session types to allow user to edit the session type

    When a session type is clicked on, this code is run and returns a form to edit the
    details. Updates are not done through here however, this just serves the form.
    """

    session_type = get_object_or_404(
        SessionType, pk=request.POST.get("session_type_id")
    )

    session_type_payment_methods = SessionTypePaymentMethod.objects.filter(
        session_type=session_type
    ).order_by("payment_method")

    # you can't use order_by in a template and prefetch related doesn't seem to support it properly, so build it here
    rates = []

    for session_type_payment_method in session_type_payment_methods:
        rates.append(
            session_type_payment_method.sessiontypepaymentmethodmembership_set.order_by(
                "session_type_payment_method", "membership__name"
            )
        )

    # HTMX values for the delete button
    hx_post = reverse("organisations:club_menu_tab_settings_session_delete_htmx")
    hx_vars = f"club_id:{club.id},session_id:{session_type.id}"

    # Don't allow the last session to be deleted
    allow_delete = SessionType.objects.filter(organisation=club).count() > 1

    return render(
        request,
        "organisations/club_menu/settings/session_edit_htmx.html",
        {
            "rates": rates,
            "session_type": session_type,
            "club": club,
            "hx_post": hx_post,
            "hx_vars": hx_vars,
            "allow_delete": allow_delete,
        },
    )


@check_club_menu_access(check_payments=True)
def club_menu_tab_settings_payment_htmx(request, club, message=""):
    """Show club payment types"""

    if "add" in request.POST:
        form = PaymentTypeForm(request.POST, club=club)

        if form.is_valid():
            payment_type = OrgPaymentMethod(
                organisation=club, payment_method=form.cleaned_data["payment_name"]
            )
            payment_type.save()

            # Update any sessions with the new payment type
            add_payment_method_session_type_combos(club)

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
        "-active", "payment_method"
    )
    misc_pay_types = MiscPayType.objects.filter(organisation=club)

    return render(
        request,
        "organisations/club_menu/settings/payment_htmx.html",
        {
            "payment_methods": payment_methods,
            "club": club,
            "form": form,
            "misc_pay_types": misc_pay_types,
            "message": message,
        },
    )


@check_club_menu_access()
def club_menu_tab_settings_venues_htmx(request, club):
    """Show club venues"""

    if "add" in request.POST:
        form = VenueForm(request.POST, club=club)

        if not rbac_user_has_role(request.user, f"orgs.org.{club.id}.edit"):
            return HttpResponse("You do not have access to add a venue")

        elif form.is_valid():
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
    """Delete a venue - well, actually just marks it as inactive"""

    venue = get_object_or_404(OrgVenue, pk=request.POST.get("venue_id"))

    # Check for this club matching the venue record
    if venue.organisation != club:
        return HttpResponse("Access denied")

    # Check for access
    if not rbac_user_has_role(request.user, f"orgs.org.{club.id}.edit"):
        return HttpResponse("You do not have access to delete a venue")

    ClubLog(
        organisation=club, actor=request.user, action=f"Deleted venue: {venue.venue}"
    ).save()

    venue.is_active = False
    venue.save()

    return club_menu_tab_settings_venues_htmx(request)


@check_club_menu_access()
def club_menu_tab_settings_toggle_payment_type_htmx(request, club):
    """toggle a payment type on or off"""

    payment_type = get_object_or_404(
        OrgPaymentMethod, pk=request.POST.get("payment_type_id")
    )

    if payment_type.active:
        # Check if this is default secondary payment for this club - shouldn't happen. HTML prevents this.
        if club.default_secondary_payment_method == payment_type:
            return HttpResponse("not allowed")
        ClubLog(
            organisation=club,
            actor=request.user,
            action=f"Disabled payment method: {payment_type.payment_method}",
        ).save()
        payment_type.active = False
        payment_type.save()

        # Delete any invalid session payment records
        turn_off_payment_type(club)
    else:
        ClubLog(
            organisation=club,
            actor=request.user,
            action=f"Activated payment method: {payment_type.payment_method}",
        ).save()
        payment_type.active = True
        payment_type.save()

        # Update any sessions with the new payment type
        add_payment_method_session_type_combos(club)

    return club_menu_tab_settings_payment_htmx(request)


@check_club_menu_access()
def club_menu_tab_settings_misc_pay_add_htmx(request, club):
    """Add a miscellaneous payment"""

    misc_pay_name = request.POST.get("misc_pay_name")
    MiscPayType(organisation=club, description=misc_pay_name).save()
    ClubLog(
        organisation=club,
        actor=request.user,
        action=f"Added miscellaneous payment type: {misc_pay_name}",
    ).save()

    return club_menu_tab_settings_payment_htmx(request)


@check_club_menu_access()
def club_menu_tab_settings_misc_pay_delete_htmx(request, club):
    """Add a miscellaneous payment"""

    misc_pay_id = request.POST.get("misc_pay_id")
    misc_pay = get_object_or_404(MiscPayType, pk=misc_pay_id)
    ClubLog(
        organisation=club,
        actor=request.user,
        action=f"Deleted miscellaneous payment type: {misc_pay.description}",
    ).save()
    misc_pay.delete()

    return club_menu_tab_settings_payment_htmx(request)


@check_club_menu_access()
def club_menu_tab_settings_misc_pay_amount_htmx(request, club):
    """Change the default amount of a miscellaneous payment"""

    misc_pay_id = request.POST.get("misc_pay_id")
    misc_pay = get_object_or_404(MiscPayType, pk=misc_pay_id)
    amount = request.POST.get("misc_pay_amount", 0)

    ClubLog(
        organisation=club,
        actor=request.user,
        action=f"Updated miscellaneous payment type: {misc_pay.description}. Amount set to {amount}.",
    ).save()
    misc_pay.default_amount = amount
    misc_pay.save()

    return club_menu_tab_settings_payment_htmx(request, "Amount updated")


@check_club_menu_access()
def club_menu_tab_settings_table_fee_update_htmx(request, club):
    """Change table fees"""

    if not rbac_user_has_role(request.user, f"orgs.org.{club.id}.edit"):
        return HttpResponse("You do not have access to change rates")

    session = get_object_or_404(
        SessionTypePaymentMethodMembership, pk=request.POST.get("session_id")
    )
    fee = request.POST.get("fee")
    session.fee = fee
    session.save()

    if session.membership:
        membership_name = session.membership.name
    else:
        membership_name = "Non-member"

    ClubLog(
        organisation=club,
        actor=request.user,
        action=f"Changed session fee for {membership_name} {session.session_type_payment_method.payment_method.payment_method} to {fee}",
    ).save()

    return HttpResponse("Data saved")


@check_club_menu_access()
def club_menu_tab_settings_session_delete_htmx(request, club, check_org_edit=True):
    """Delete entire session"""

    session = get_object_or_404(SessionType, pk=request.POST.get("session_id"))

    ClubLog(
        organisation=club,
        actor=request.user,
        action=f"Deleted session {session}",
    ).save()

    session.delete()

    return club_menu_tab_settings_sessions_htmx(request)


@check_club_menu_access(check_org_edit=True)
def club_menu_tab_settings_session_add_htmx(request, club):
    """Add new session"""

    print("inside")

    session_name = request.POST.get("session_name")

    add_club_session(club, session_name)

    ClubLog(
        organisation=club,
        actor=request.user,
        action=f"Added session {session_name}",
    ).save()

    return club_menu_tab_settings_sessions_htmx(request)


@check_club_menu_access(check_comms=True)
def tags_htmx(request, club):
    """build the comms tags tab in club menu"""

    if "add" in request.POST:
        form = TagForm(request.POST, club=club)

        if form.is_valid():
            ClubTag.objects.get_or_create(
                organisation=club, tag_name=form.cleaned_data["tag_name"]
            )
            # reset form
            form = TagForm(club=club)
    else:
        form = TagForm(club=club)

    tags = (
        ClubTag.objects.prefetch_related("memberclubtag_set")
        .filter(organisation=club)
        .order_by("tag_name")
    )

    # Add on count of how many members have this tag
    for tag in tags:
        tag.uses = MemberClubTag.objects.filter(club_tag=tag).count()
        tag.hx_post = reverse("organisations:club_menu_tab_comms_tags_delete_tag_htmx")
        tag.hx_vars = f"club_id:{club.id},tag_id:{tag.id}"

    return render(
        request,
        "organisations/club_menu/settings/tags_htmx.html",
        {
            "club": club,
            "tags": tags,
            "form": form,
        },
    )


@check_club_menu_access(check_comms=True)
def templates_htmx(request, club, edit_template=None, message=None):
    """build the comms template tab in club menu. The edit forms pass in a value for edit_template so
    we can re-open it"""

    templates = OrgEmailTemplate.objects.filter(organisation=club).order_by("pk")

    # Add htmx tags
    for template in templates:
        template.hx_post = reverse(
            "organisations:club_menu_tab_settings_delete_template_htmx"
        )
        template.hx_vars = f"club_id:{club.id}, template_id:{template.id}"

    return render(
        request,
        "organisations/club_menu/settings/templates_htmx.html",
        {
            "club": club,
            "templates": templates,
            "template": edit_template,
            "message": message,
        },
    )


def _next_template_name(club):
    """get the next default template name - "New Template" or "New Template(2)" etc"""

    last_default_template = (
        OrgEmailTemplate.objects.filter(template_name__startswith="New Template")
        .order_by("template_name")
        .last()
    )

    if not last_default_template:
        return "New Template"

    if last_default_template.template_name == "New Template":
        return "New Template(1)"

    try:  # usual case of New Template(n)
        number_and_last_bracket = last_default_template.template_name[13:]
        number = int(number_and_last_bracket[:-1])
        return f"New Template({number + 1})"
    except ValueError:  # Error case e.g. New Template Julian
        append = "".join(random.choices(string.ascii_uppercase + string.digits, k=3))
        return f"New Template({append})"


@check_club_menu_access(check_comms=True)
def edit_template_htmx(request, club):
    """HTMX form to render the email template edit screen. We create a new template if one isn't provided"""

    # Try to load existing template
    template_id = request.POST.get("template_id")

    if template_id:
        template = get_object_or_404(OrgEmailTemplate, pk=template_id)
        message = "Editing template"
    else:
        # Create new template
        template_name = _next_template_name(club)
        template = OrgEmailTemplate(
            organisation=club,
            template_name=template_name,
            last_modified_by=request.user,
            from_name=f"{club}",
        )
        template.save()
        message = "Created new template"

    if "save" in request.POST:
        form = TemplateForm(request.POST, instance=template)
        if form.is_valid():
            template = form.save(commit=False)
            template.last_modified_by = request.user
            template.save()
        else:
            print(form.errors)

    # We need to reload the template form even if we have saved it or fonts with
    # more than one word (e.g. "Times New Roman") get corrupted
    form = TemplateForm(instance=template)

    # We don't handle the banner form in here, it has its own function
    banner_form = TemplateBannerForm(instance=template)

    response = render(
        request,
        "organisations/club_menu/settings/template_form_htmx.html",
        {
            "club": club,
            "form": form,
            "banner_form": banner_form,
            "template": template,
            "message": message,
        },
    )

    # Use HX-Trigger to update the list of templates
    response["HX-Trigger"] = "update_template_list"

    return response


@check_club_menu_access(check_comms=True)
def template_list_htmx(request, club):
    """Returns a list of templates to update the top part of the tempaltes view in Settings when things change"""

    templates = OrgEmailTemplate.objects.filter(organisation=club).order_by("pk")

    # Add htmx tags
    for template in templates:
        template.hx_post = reverse(
            "organisations:club_menu_tab_settings_delete_template_htmx"
        )
        template.hx_vars = f"club_id:{club.id}, template_id:{template.id}"

    return render(
        request,
        "organisations/club_menu/settings/templates_list_htmx.html",
        {
            "club": club,
            "templates": templates,
        },
    )


@login_required()
def template_preview_htmx(request):
    """Preview a template as user creates it"""

    template_id = request.POST.get("template_id")
    template = get_object_or_404(OrgEmailTemplate, pk=template_id)

    return render(
        request,
        "organisations/club_menu/settings/template_preview_htmx.html",
        {"template": template, "host": COBALT_HOSTNAME},
    )


@check_club_menu_access(check_comms=True)
def edit_template_name_htmx(request, club):
    """Edit the template_name field on a template"""

    template_id = request.POST.get("template_id")
    template = get_object_or_404(OrgEmailTemplate, pk=template_id)
    if template.organisation != club:
        return HttpResponse("Access Denied")

    name = request.POST.get("template_name")

    if OrgEmailTemplate.objects.filter(template_name=name).exists():
        return templates_htmx(
            request, edit_template=template, message="Template name in use"
        )

    template.template_name = name
    template.save()

    return templates_htmx(request, edit_template=template)


@check_club_menu_access(check_comms=True)
def edit_from_name_htmx(request, club):
    """Edit the from_name field on a template"""

    template_id = request.POST.get("template_id")
    template = get_object_or_404(OrgEmailTemplate, pk=template_id)
    if template.organisation != club:
        return HttpResponse("Access Denied")

    from_name = request.POST.get("from_name")
    template.from_name = from_name
    template.save()

    return templates_htmx(request, edit_template=template)


@check_club_menu_access(check_comms=True)
def edit_reply_to_htmx(request, club):
    """Edit the reply_to field on a template"""

    template_id = request.POST.get("template_id")
    template = get_object_or_404(OrgEmailTemplate, pk=template_id)
    if template.organisation != club:
        return HttpResponse("Access Denied")

    reply_to = request.POST.get("reply_to")
    template.reply_to = reply_to
    template.save()

    return templates_htmx(request, edit_template=template)


@check_club_menu_access(check_comms=True)
def edit_template_banner_htmx(request, club):
    """Edit the template_name field on a template"""

    template_id = request.POST.get("template_id")
    template = get_object_or_404(OrgEmailTemplate, pk=template_id)
    if template.organisation != club:
        return HttpResponse("Access Denied")

    template_form = TemplateBannerForm(request.POST, request.FILES, instance=template)
    if template_form.is_valid():
        template = template_form.save()

    return templates_htmx(request, edit_template=template)


@check_club_menu_access(check_comms=True)
def delete_template_htmx(request, club):
    """Delete a template"""

    template_id = request.POST.get("template_id")
    template = get_object_or_404(OrgEmailTemplate, pk=template_id)
    if template.organisation != club:
        return HttpResponse("Access Denied")

    template.delete()

    return templates_htmx(request)


@check_club_menu_access(check_comms=True)
def welcome_pack_htmx(request, club, message=None):
    """Manage welcome packs for new members"""

    # Clubs can only have one welcome pack
    welcome_pack = WelcomePack.objects.filter(organisation=club).first()

    # set up hx_vars for template
    hx_vars = f"club_id:{club.id},delete:delete"

    return render(
        request,
        "organisations/club_menu/settings/welcome_pack_htmx.html",
        {
            "club": club,
            "message": message,
            "welcome_pack": welcome_pack,
            "hx_vars": hx_vars,
        },
    )


@check_club_menu_access(check_comms=True)
def welcome_pack_edit_htmx(request, club):
    """Manage welcome packs for new members"""

    message = ""

    # Clubs can only have one welcome pack, get or create it
    welcome_pack = WelcomePack.objects.filter(organisation=club).first()

    if not welcome_pack:
        welcome_pack = WelcomePack(
            organisation=club, last_modified_by=request.user, updated_at=timezone.now()
        )
        welcome_pack.save()
        message = "Welcome Email Created"

    if "save" in request.POST:
        welcome_form = WelcomePackForm(request.POST, instance=welcome_pack, club=club)

        if welcome_form.is_valid():
            welcome_pack = welcome_form.save(commit=False)
            welcome_pack.last_updated_by = request.user
            welcome_pack.last_updated = timezone.localtime()
            welcome_pack.save()
            message = "Welcome Email Saved"
        else:
            message = welcome_form.errors

        return welcome_pack_htmx(request, message=message)

    elif "test" in request.POST:
        _send_welcome_pack(
            club,
            request.user.first_name,
            request.user.email,
            request.user,
            invite_to_join=False,
        )
        return welcome_pack_htmx(
            request, message=f"Test email sent to {request.user.email}"
        )

    else:
        welcome_form = WelcomePackForm(instance=welcome_pack, club=club)

    return render(
        request,
        "organisations/club_menu/settings/welcome_pack_edit_htmx.html",
        {
            "club": club,
            "message": message,
            "welcome_pack": welcome_pack,
            "welcome_form": welcome_form,
        },
    )


@check_club_menu_access(check_comms=True)
def welcome_pack_delete_htmx(request, club):
    """Delete the welcome pack"""

    WelcomePack.objects.filter(organisation=club).first().delete()

    return welcome_pack_htmx(request, message="Welcome Email Deleted")


@check_club_menu_access(check_comms=True)
def users_with_tag_htmx(request, club, partial=False):
    """Add and remove members from tags. This is the main form and view

    The partial parameter is used if we only want to return the list of users with this tag and not the whole form.
    This is used when we add a user so we can update the displayed list but stay on the same screen to add more.
    """

    tag_id = request.POST.get("tag_id")
    tag = get_object_or_404(ClubTag, pk=tag_id)

    system_numbers = MemberClubTag.objects.filter(club_tag=tag).values("system_number")

    users_with_tag = get_club_members_from_system_number_list(system_numbers, club)

    # We need the list of members without the tag for the add function
    all_members = get_members_for_club(club)

    # Check if this club has members to avoid showing edit options that won't work
    club_has_members = bool(all_members)

    # build list of tagged users
    users_with_tag_list = [
        user_with_tag.system_number for user_with_tag in users_with_tag
    ]

    users_without_tag = [
        member
        for member in all_members
        if member.system_number not in users_with_tag_list
    ]

    # Add HTMX fields
    hx_post = reverse("organisations:club_menu_tab_settings_delete_user_from_tag_htmx")
    for user_with_tag in users_with_tag:
        user_with_tag.hx_vars = f"{{'club_id':{club.id}, 'system_number':{user_with_tag.system_number}, 'tag_id':{tag.id} }}"

    if partial:
        template = "organisations/club_menu/settings/users_with_tag_sub_htmx.html"
    else:
        template = "organisations/club_menu/settings/users_with_tag_htmx.html"

    return render(
        request,
        template,
        {
            "users_with_tag": users_with_tag,
            "users_without_tag": users_without_tag,
            "tag": tag,
            "club": club,
            "hx_post": hx_post,
            "club_has_members": club_has_members,
        },
    )


@check_club_menu_access(check_comms=True)
def delete_user_from_tag_htmx(request, club):
    """Remove a tag from a user"""

    system_number = request.POST.get("system_number")
    tag_id = request.POST.get("tag_id")

    club_tag = get_object_or_404(ClubTag, pk=tag_id)

    # Reject if not a tag for this club
    if club_tag.organisation != club:
        return HttpResponse("Access Denied")

    MemberClubTag.objects.filter(
        club_tag=club_tag, system_number=system_number
    ).delete()

    return users_with_tag_htmx(request)


@check_club_menu_access(check_comms=True)
def add_user_to_tag_htmx(request, club):
    """Add a tag to a user"""

    system_number = request.POST.get("system_number")
    tag_id = request.POST.get("tag_id")

    club_tag = get_object_or_404(ClubTag, pk=tag_id)

    # Reject if not a tag for this club
    if club_tag.organisation != club:
        return HttpResponse("Access Denied")

    MemberClubTag(club_tag=club_tag, system_number=system_number).save()

    return users_with_tag_htmx(request, partial=True)


@check_club_menu_access(check_payments=True)
def club_menu_tab_settings_payment_edit_name_htmx(request, club):
    """Edit the name of a payment method. Returns th whole section"""

    payment_method = get_object_or_404(
        OrgPaymentMethod, pk=request.POST.get("payment_method_id")
    )
    if payment_method.organisation != club:
        return HttpResponse("Access denied")

    new_name = request.POST.get("new_name")

    payment_method.payment_method = new_name
    payment_method.save()

    return club_menu_tab_settings_payment_htmx(request)


@check_club_menu_access(check_comms=True)
def club_menu_tab_settings_tag_edit_name_htmx(request, club):
    """Edit the name of a tag. Returns the whole section"""

    tag = get_object_or_404(ClubTag, pk=request.POST.get("tag_id"))
    if tag.organisation != club:
        return HttpResponse("Access denied")

    new_name = request.POST.get("new_tag_name")

    tag.tag_name = new_name
    tag.save()

    return tags_htmx(request)


@check_club_menu_access(check_comms=True)
def add_all_members_to_tag_htmx(request, club):
    """Add a tag to all members of a club. Returns the users with tag section"""

    club_tag = get_object_or_404(ClubTag, pk=request.POST.get("tag_id"))

    if club_tag.organisation != club:
        return HttpResponse("Incorrect tag value for this club")

    all_members = MemberMembershipType.objects.filter(
        membership_type__organisation=club
    )

    for member in all_members:
        member_club_tag, _ = MemberClubTag.objects.get_or_create(
            club_tag=club_tag, system_number=member.system_number
        )
        member_club_tag.save()

    return users_with_tag_htmx(request, partial=True)


@check_club_menu_access(check_org_edit=True)
def default_secondary_payment_method_htmx(request, club):
    """handle the form for club level default payment method if not Bridge Credits"""

    message = ""

    if "save" in request.POST:
        form = OrgDefaultSecondaryPaymentMethod(request.POST, club=club)

        if form.is_valid():
            default_secondary_payment_method = form.cleaned_data[
                "default_secondary_payment_method"
            ]
            club.default_secondary_payment_method = default_secondary_payment_method
            club.save()

            ClubLog(
                organisation=club,
                actor=request.user,
                action=f"Changed default secondary payment method to: {default_secondary_payment_method}",
            ).save()
            message = "Change saved"
        else:
            print(form.errors)

    form = OrgDefaultSecondaryPaymentMethod(club=club)

    return render(
        request,
        "organisations/club_menu/settings/default_secondary_payment_method_htmx.html",
        {"form": form, "club": club, "message": message},
    )


@check_club_menu_access(check_org_edit=True)
def edit_minimum_balance_after_settlement_htmx(request, club):
    """Change the minimum balance that is left as a float after settlement"""

    form = MinimumBalanceAfterSettlementForm(request.POST, instance=club)
    message = ""

    if "save" in request.POST:

        if form.is_valid():
            club = form.save()

            ClubLog(
                organisation=club,
                actor=request.user,
                action=f"Changed minimum balance after settlement to: {club.minimum_balance_after_settlement}",
            ).save()
            message = "Change saved"
        else:
            print(form.errors)

    return render(
        request,
        "organisations/club_menu/settings/edit_minimum_balance_after_settlement_htmx.html",
        {"form": form, "club": club, "message": message},
    )
