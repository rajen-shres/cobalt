from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from cobalt.settings import GLOBAL_MPSERVER, GLOBAL_TITLE
from organisations.forms import OrgFormOld
from organisations.models import (
    Organisation,
    MemberClubEmail,
    ClubLog,
    MemberMembershipType,
    OrganisationFrontPage,
    MembershipType,
)
from payments.models import OrganisationTransaction
from rbac.core import rbac_user_has_role
from rbac.models import RBACGroupRole
from rbac.views import rbac_forbidden
from utils.views.general import masterpoint_query


def org_balance(org, text=None):
    """return organisation balance. If balance is zero return 0.0 unless
    text is True, then return "Nil" """

    # get balance
    last_tran = OrganisationTransaction.objects.filter(organisation=org).last()
    if last_tran:
        return last_tran.balance
    else:
        return "Nil" if text else 0.0


def compare_form_with_mpc(form, club):
    """Compare data on this form with values from the Masterpoints Centre and flag any differences"""

    # Get the data from the MPC
    club_data = get_club_data_from_masterpoints_centre(club.org_id)

    if club_data:

        # Add our own fields for warnings to the form
        form.warnings = {}

        for item in [
            "club_email",
            "address1",
            "address2",
            "postcode",
            "club_website",
            "suburb",
            "name",
        ]:
            try:
                if form[item].value() != club_data[item]:
                    # We can get None and empty string "". Treat as equal
                    if form[item].value() is None and club_data[item] == "":
                        continue
                    form.warnings[item] = "Warning: This value doesn't match the MPC"
            except KeyError:
                pass
    return form


def get_club_data_from_masterpoints_centre(club_number):
    """Get data about a club from the Masterpoints Centre

    Args:
        club_number: ABF club number

    Returns: dictionary of values
    """

    # Try to load data from MP Server
    qry = f"{GLOBAL_MPSERVER}/clubDetails/{club_number}"
    club_details = masterpoint_query(qry)

    if len(club_details) > 0:
        club_details = club_details[0]

    club_data = {}

    if club_details:
        club_data = {
            "name": club_details["ClubName"],
            "club_secretary": club_details["ClubSecName"].strip(),
            "state": club_details["VenueState"],
            "postcode": club_details["VenuePostcode"],
            "club_email": club_details["ClubEmail"],
            "club_website": club_details["ClubWebsite"],
            "address1": club_details["VenueAddress1"],
            "address2": club_details["VenueAddress2"],
            "suburb": club_details["VenueSuburb"],
            "org_id": club_number,
        }

    return club_data


def get_rbac_model_for_state(state):
    """Take in a state name e.g. NSW and return the model that maps to that organisation.
    Assumes one state organisation per state."""

    state_org = Organisation.objects.filter(state=state).filter(type="State")

    if not state_org:
        return None

    if state_org.count() > 1:
        raise ImproperlyConfigured

    return state_org.first().id


# TODO: Retire this
@login_required()
def org_edit(request, org_id):
    """Edit details about an organisation OLD - REMOVE ONCE NEW CLUB ADMIN IS DONE

    Args:
        org_id - organisation to edit

    Returns:
        HttpResponse - page to edit organisation
    """
    if not (
        rbac_user_has_role(request.user, "orgs.org.%s.edit" % org_id)
        or rbac_user_has_role(request.user, "orgs.admin.edit")
    ):
        return rbac_forbidden(request, "orgs.org.%s.edit" % org_id)

    org = get_object_or_404(Organisation, pk=org_id)

    if request.method == "POST":

        form = OrgFormOld(request.POST, instance=org)
        if form.is_valid():
            org = form.save(commit=False)
            org.last_updated_by = request.user
            org.last_updated = timezone.localtime()
            org.save()
            messages.success(
                request, "Changes saved", extra_tags="cobalt-message-success"
            )

    else:
        form = OrgFormOld(instance=org)

    return render(request, "organisations/edit_org.html", {"form": form})


def club_staff(user):
    """Used by dashboard. Returns the first club found that this user is a staff member for or None

    Note: Staff with orgs.org.all rather than orgs.org.<model_id>.all will not get an icon (returns None)

    Args:
        user: User objects

    Returns:
        model_id: If not None then model_id is the first organisation that this user has access to
    """

    access = (
        RBACGroupRole.objects.filter(group__rbacusergroup__member=user)
        .filter(app="orgs")
        .filter(model="org")
        .values_list("model_id")
        .last()
    )

    # We return the latest added access, should maybe allow a user preference here

    if access:
        return access[0]  # first item in tuple (model_id)

    return None


def replace_unregistered_user_with_real_user(real_user: User):
    """All the data is keyed off system_number so all we really need to do is to delete club emails.

    The calling function deletes the unregistered user"""

    MemberClubEmail.objects.filter(system_number=real_user.system_number).delete()

    # Logs
    clubs = MemberMembershipType.objects.filter(system_number=real_user.system_number)
    for club in clubs:
        ClubLog(
            actor=real_user,
            organisation=club.membership_type.organisation,
            action=f"{real_user} registered for {GLOBAL_TITLE}. Unregistered user replaced with real user.",
        )


def active_email_for_un_reg(un_reg, club):
    """returns email for user"""

    member_club_email = MemberClubEmail.objects.filter(
        system_number=un_reg.system_number
    ).first()

    return member_club_email.email if member_club_email else None


@login_required()
def org_profile(request, org_id):
    """Show public profile for organisation"""
    org = get_object_or_404(Organisation, pk=org_id)

    # create or get the front page
    front_page, _ = OrganisationFrontPage.objects.get_or_create(organisation=org)

    # Replace tokens with code
    url = reverse("results:show_results_for_club_htmx")
    results = f""" <div hx-post="{url}" hx-vars="club_id:{org.id}" hx-trigger="load" id="club-results"></div> """

    front_page.summary = front_page.summary.replace("{{ RESULTS }}", results)

    url = reverse("events:show_congresses_for_club_htmx")
    congresses = f""" <div hx-post="{url}" hx-vars="club_id:{org.id}" hx-trigger="load" id="club-congresses"></div> """

    front_page.summary = front_page.summary.replace("{{ CONGRESSES }}", congresses)

    # See if this user is an admin for this club
    is_admin = is_admin_for_organisation(request.user, org)

    return render(
        request,
        "organisations/org_profile.html",
        {"org": org, "front_page": front_page, "is_admin": is_admin},
    )


def is_admin_for_organisation(user, club):
    """Boolean. Does this user have admin access to this club"""

    # Check for state level access
    rbac_model_for_state = get_rbac_model_for_state(club.state)
    state_role = f"orgs.state.{rbac_model_for_state}.edit"
    if rbac_user_has_role(user, state_role):
        return True

    # Check for global role
    if rbac_user_has_role(user, "orgs.admin.edit"):
        return True

    # Check for club level access
    club_role = f"orgs.org.{club.id}.view"
    if rbac_user_has_role(user, club_role):
        return True

    return False


def get_clubs_for_player(player):
    """Return a list of clubs that this user is a member of. Strictly returns a MembershipType queryset."""

    memberships = MemberMembershipType.objects.filter(
        system_number=player.system_number
    ).values_list("membership_type")

    return MembershipType.objects.filter(id__in=memberships)


def get_membership_type_for_players(system_number_list, club):
    """returns the membership type for a list of system_numbers. It returns a dict of system_number to
    membership type name e.g. "Standard"

    Guests will not be in the dictionary

    """

    membership_types = (
        MemberMembershipType.objects.select_related("membership_type")
        .filter(system_number__in=system_number_list)
        .filter(membership_type__organisation=club)
    )

    return {
        membership_type.system_number: membership_type.membership_type.name
        for membership_type in membership_types
    }


def get_membership_for_player(system_number, club):
    """returns the MembershipType object for a system_number."""

    member_membership_type = (
        MemberMembershipType.objects.select_related("membership_type")
        .filter(system_number=system_number)
        .filter(membership_type__organisation=club)
    ).first()

    if member_membership_type:
        return member_membership_type.membership_type

    return None


@login_required()
def generic_org_search_htmx(request):
    """basic search for organisation by name

    We accept a few parameters passed in through hx-vars:

    hidden_id_field: field to put the org id into
    display_name: field to put the name of the org into
    return_trigger: trigger to call when we return

    """

    search = request.POST.get("org_search_htmx")

    if not search:
        return HttpResponse("")

    org_matches = Organisation.objects.filter(name__istartswith=search)[:11]

    # we get 11 but show 10, so we know if there are more
    more = len(org_matches) == 11

    if org_matches.count() == 1:
        print("Unique")

    # Get extra values
    hidden_id_field = request.POST.get("hidden_id_field")
    display_name = request.POST.get("display_name")
    select_callback = request.POST.get("select_callback")
    hx_target = request.POST.get("hx_target")

    return render(
        request,
        "organisations/htmx_search/search_results_htmx.html",
        {
            "org_matches": org_matches[:10],
            "more": more,
            "display_name": display_name,
            "hidden_id_field": hidden_id_field,
            "select_callback": select_callback,
            "hx_target": hx_target,
        },
    )


def get_org_statistics():
    """return stats on organisations. called by utils statistics"""

    total_clubs = Organisation.objects.filter(type="Club").count()
    total_orgs = Organisation.objects.count()

    return {
        "total_clubs": total_clubs,
        "total_orgs": total_orgs,
    }
