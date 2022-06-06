from pprint import pprint

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from accounts.models import UnregisteredUser, User
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
from rbac.models import RBACUserGroup, RBACGroupRole
from rbac.views import rbac_forbidden
from utils.views import masterpoint_query


@login_required()
def home(request):
    """Home page for the organisations' app - called from the sidebar"""

    return render(request, "organisations/general/home.html")


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
    )

    # We return the latest added access, should maybe allow a user preference here

    if access:
        return access.last()[0]  # first item in tuple (model_id)

    return None


def replace_unregistered_user_with_real_user(real_user: User):
    """All the data is keyed off system_number so all we really need to do is to delete club emails.

    The calling function deletes the unregistered user"""

    MemberClubEmail.objects.filter(system_number=real_user.system_number).delete()

    # Logs
    clubs = MemberMembershipType.objects.active().filter(
        system_number=real_user.system_number
    )
    for club in clubs:
        ClubLog(
            actor=real_user,
            organisation=club.membership_type.organisation,
            action=f"{real_user} registered for {GLOBAL_TITLE}. Unregistered user replaced with real user.",
        )


def _active_email_for_un_reg(un_reg, club):
    """returns either this email or an overridden one for the club"""
    club_email = MemberClubEmail.objects.filter(
        system_number=un_reg.system_number
    ).first()
    if club_email:
        return club_email.email
    return un_reg.email


def org_profile(request, org_id):
    """Show public profile for organisation"""
    org = get_object_or_404(Organisation, pk=org_id)
    front_page, _ = OrganisationFrontPage.objects.get_or_create(organisation=org)
    return render(
        request,
        "organisations/org_profile.html",
        {"org": org, "front_page": front_page},
    )


def get_clubs_for_player(player):
    """Return a list of clubs that this user is a member of. Strictly returns a MembershipType queryset."""

    memberships = (
        MemberMembershipType.objects.active()
        .filter(system_number=player.system_number)
        .values_list("membership_type")
    )

    return MembershipType.objects.filter(id__in=memberships)


def get_membership_type_for_players(system_number_list, club):
    """returns the membership type for a list of system_numbers. It returns a dict of system_number to
    membership type name e.g. "Standard" """

    membership_types = (
        MemberMembershipType.objects.active()
        .filter(system_number__in=system_number_list)
        .filter(membership_type__organisation=club)
    )

    return {
        membership_type.system_number: membership_type.membership_type.name
        for membership_type in membership_types
    }
