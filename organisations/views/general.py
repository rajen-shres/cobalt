from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from organisations.forms import OrgFormOld
from organisations.models import Organisation
from payments.models import OrganisationTransaction
from rbac.core import rbac_user_has_role
from rbac.models import RBACUserGroup, RBACGroupRole
from rbac.views import rbac_forbidden


def org_balance(org, text=None):
    """return organisation balance. If balance is zero return 0.0 unless
    text is True, then return "Nil" """

    # get balance
    last_tran = OrganisationTransaction.objects.filter(organisation=org).last()
    if last_tran:
        return last_tran.balance
    else:
        return "Nil" if text else 0.0


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
