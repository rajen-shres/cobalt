from pprint import pprint

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from accounts.models import UnregisteredUser, User
from cobalt.settings import GLOBAL_MPSERVER
from organisations.forms import OrgFormOld
from organisations.models import Organisation
from payments.models import OrganisationTransaction
from rbac.core import rbac_user_has_role
from rbac.models import RBACUserGroup, RBACGroupRole
from rbac.views import rbac_forbidden
from utils.views import masterpoint_query


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

    Args:
        user: User objects

    Returns:
        group: RBACGroupRole. If not None then model_id is the first organisation that this user has access to

    """

    return (
        RBACGroupRole.objects.filter(group__rbacusergroup__member=user)
        .filter(app="orgs")
        .filter(model="org")
        .first()
    )


def replace_unregistered_user_with_real_user(
    unregistered_user: UnregisteredUser, real_user: User
):
    """We don't take any data across from the user, but we do update the links"""

    # Call the callbacks - add later
    print("Unregistered:", unregistered_user)
    print("User:", real_user)
