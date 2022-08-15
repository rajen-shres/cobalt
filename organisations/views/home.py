from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from organisations.models import Organisation, MemberMembershipType
from rbac.models import RBACGroupRole


@login_required()
def home(request):
    """Home page for the organisations' app - called from the sidebar"""

    # See if an admin
    admin_club_ids = (
        RBACGroupRole.objects.filter(group__rbacusergroup__member=request.user)
        .filter(group__name_qualifier__contains="clubs.generated")
        .values("model_id")
        .distinct()
    )
    if admin_club_ids.exists():
        admin_for_clubs = Organisation.objects.filter(pk__in=admin_club_ids)
    else:
        admin_for_clubs = None

    # Get club memberships
    memberships = MemberMembershipType.objects.select_related(
        "membership_type__organisation"
    ).filter(system_number=request.user.system_number)

    # Get all clubs (only 300)
    clubs = Organisation.objects.filter(type="Club", status="Open")

    return render(
        request,
        "organisations/home/home.html",
        {
            "admin_for_clubs": admin_for_clubs,
            "memberships": memberships,
            "clubs": clubs,
        },
    )
