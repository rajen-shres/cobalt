import requests
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string

from cobalt.settings import GLOBAL_MPSERVER, GLOBAL_TITLE
from rbac.core import rbac_user_has_role
from .forms import OrgForm
from .models import Organisation
from .views import _get_rbac_model_for_state


@login_required()
def org_search_ajax(request):
    """Ajax org search function. Used by the generic org search.

    Args:
        orgname - partial org name to search for.

    Returns:
        HttpResponse - either a message or a list of users in HTML format.
    """

    msg = ""

    if request.method == "GET":

        if "orgname" not in request.GET:
            return HttpResponse("orgname missing from request")
        else:
            search_org_name = request.GET.get("orgname")
            orgs = Organisation.objects.filter(name__icontains=search_org_name)

        if request.is_ajax:
            if orgs.count() > 30:
                msg = "Too many results (%s)" % orgs.count()
                orgs = None
            elif orgs.count() == 0:
                msg = "No matches found"
            html = render_to_string(
                template_name="organisations/org_search_ajax.html",
                context={"orgs": orgs, "msg": msg},
            )

            data_dict = {"data": html}

            return JsonResponse(data=data_dict, safe=False)

    return HttpResponse("invalid request")


@login_required()
def org_detail_ajax(request):
    """Returns basic info on an org for the generic org search.

    Ajax call to get basic info on an org. Will return an empty json array
    if the org number is invalid.

    Args:
        org_id - org number

    Returns:
        Json array: address etc.
    """

    if request.method == "GET" and "org_id" in request.GET:
        org_id = request.GET.get("org_id")
        org = get_object_or_404(Organisation, pk=org_id)
        if request.is_ajax:
            html = render_to_string(
                template_name="organisations/org_detail_ajax.html",
                context={"org": org},
            )
            data_dict = {"data": html, "org": org.name}
            return JsonResponse(data=data_dict, safe=False)
    return JsonResponse(data={"error": "Invalid request"})


@login_required()
def get_club_details_ajax(request):
    """Get details about club from Masterpoints centre"""

    if request.method != "POST" or "club_number" not in request.POST:
        return

    club_number = request.POST.get("club_number")

    # initialise return data
    errors = None
    data = {}

    # check if already exists
    if Organisation.objects.filter(org_id=club_number).exists():
        errors = f"Club already exists in {GLOBAL_TITLE}"
    else:
        # Try to load data from MP Server
        qry = f"{GLOBAL_MPSERVER}/clubDetails/{club_number}"

        try:
            club_details = requests.get(qry).json()[0]
        except (
            IndexError,
            requests.exceptions.InvalidSchema,
            requests.exceptions.MissingSchema,
            ConnectionError,
        ):
            club_details = []

        if club_details:

            print(club_details)
            print(club_details["ClubName"])

            data = {
                "name": club_details["ClubName"],
                "state": club_details["VenueState"],
                "postcode": club_details["VenuePostcode"],
            }

            # Finally we can check security - need to have access for this state

            state = data["state"]
            rbac_model_for_state = _get_rbac_model_for_state(state)

            if not (
                rbac_user_has_role(
                    request.user, "orgs.org.%s.edit" % rbac_model_for_state
                )
                or rbac_user_has_role(request.user, "orgs.admin.edit")
            ):
                errors = f"You don't have access to add a club to this state ({state})"

        else:
            errors = "Club not found"

    form = OrgForm(initial=data)

    return render(
        request,
        "organisations/admin_add_club_ajax.html",
        {"form": form, "club_number": club_number, "errors": errors},
    )
