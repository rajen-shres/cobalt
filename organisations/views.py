from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib import messages

from accounts.models import User
from events.models import CongressMaster
from rbac.models import RBACGroupRole
from .models import Organisation
from rbac.core import rbac_user_has_role, rbac_get_group_by_name
from rbac.views import rbac_forbidden
from .forms import OrgForm, OrgFormOld
from payments.models import OrganisationTransaction


def get_rbac_model_for_state(state):
    """Take in a state name e.g. NSW and return the model that maps to that organisation.
    Assumes one state organisation per state."""

    state_org = Organisation.objects.filter(state=state).filter(type="State")

    if not state_org:
        return None

    if state_org.count() > 1:
        raise ImproperlyConfigured

    return state_org.first().id


@login_required()
def org_edit(request, org_id):
    """Edit details about an organisation

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


def org_balance(org, text=None):
    """return organisation balance. If balance is zero return 0.0 unless
    text is True, then return "Nil" """

    # get balance
    last_tran = OrganisationTransaction.objects.filter(organisation=org).last()
    if last_tran:
        return last_tran.balance
    else:
        return "Nil" if text else 0.0


@login_required()
def org_portal(request, org_id):
    """Edit details about an organisation

    Args:
        org_id - organisation to view

    Returns:
        HttpResponse - page to edit organisation
    """
    if not rbac_user_has_role(request.user, "orgs.org.%s.edit" % org_id):
        return rbac_forbidden(request, "orgs.org.%s.edit" % org_id)

    org = get_object_or_404(Organisation, pk=org_id)
    congresses = CongressMaster.objects.filter(org=org)
    rbac_groups = (
        RBACGroupRole.objects.filter(app="events")
        .filter(model="org")
        .filter(model_id=org_id)
    )

    return render(
        request,
        "organisations/club_portal.html",
        {"org": org, "congresses": congresses, "rbac_groups": rbac_groups},
    )


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
            request, "{org.name} created", extra_tags="cobalt-message-success"
        )
        return redirect("organisations:admin_add_club")

    print(form.errors)

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


@login_required()
def admin_club_rbac(request, club_id):
    """Manage RBAC basic set up for a Club

    This doesn't control who gets access - clubs can do that themselves, this controls whether it is basic
    or advanced RBAC configuration. It is the RBAC structure, not the content.

    """

    # Get club
    club = get_object_or_404(Organisation, pk=club_id)

    # Get model id for this state
    rbac_model_for_state = get_rbac_model_for_state(club.state)

    # Check access
    role = "orgs.state.%s.edit" % rbac_model_for_state
    if not (
        rbac_user_has_role(request.user, role)
        or rbac_user_has_role(request.user, "orgs.admin.edit")
    ):
        return rbac_forbidden(request, role)

    # Check rbac setup

    # Simple is e.g. rbac.orgs.clubs.nsw.34.basic (we can't use the club name as it might change, use pk)
    rbac_simple = rbac_get_group_by_name(
        "rbac.orgs.clubs.%s.%s.basic" % (club.state.lower(), club.id)
    )

    # Advanced has a few groups e.g. rbac.orgs.clubs.nsw.34.managers
    # managers will always exist
    rbac_advanced = rbac_get_group_by_name(
        "rbac.orgs.clubs.%s.%s.managers" % (club.state.lower(), club.id)
    )

    error = ""
    new_setup = False

    if rbac_advanced and rbac_simple:
        error = "Error: This club is set up with both simple and advanced RBAC. Contact Support."

    if not rbac_advanced and not rbac_simple:
        error = "RBAC not set up yet."
        new_setup = True

    return render(
        request,
        "organisations/admin_club_rbac.html",
        {
            "club": club,
            "new_setup": new_setup,
            "rbac_simple": rbac_simple,
            "rbac_advanced": rbac_advanced,
            "error": error,
        },
    )
