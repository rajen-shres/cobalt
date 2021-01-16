from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.contrib import messages
from .models import Organisation
from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden
from .forms import OrgForm
from payments.models import OrganisationTransaction


@login_required()
def org_search_ajax(request):
    """ Ajax org search function. Used by the generic org search.

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
    """ Returns basic info on an org for the generic org search.

    Ajax call to get basic info on an org. Will return an empty json array
    if the org number is invalid.

    Args:
        org_id - org number

    Returns:
        Json array: address etc.
    """

    if request.method == "GET":
        if "org_id" in request.GET:
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
def org_edit(request, org_id):
    """ Edit details about an organisation

    Args:
        org_id - organisation to edit

    Returns:
        HttpResponse - page to edit organisation
    """
    if not rbac_user_has_role(request.user, "orgs.org.%s.edit" % org_id):
        return rbac_forbidden(request, "orgs.org.%s.edit" % org_id)

    org = get_object_or_404(Organisation, pk=org_id)

    if request.method == "POST":

        form = OrgForm(request.POST, instance=org)
        if form.is_valid():

            org = form.save(commit=False)
            org.last_updated_by = request.user
            org.last_updated = timezone.localtime()
            org.save()
            messages.success(
                request, "Changes saved", extra_tags="cobalt-message-success"
            )

    else:
        form = OrgForm(instance=org)

    return render(request, "organisations/edit_org.html", {"form": form})


def org_balance(org, text=None):
    """ return organisation balance. If balance is zero return 0.0 unless
        text is True, then return "Nil" """

    # get balance
    last_tran = OrganisationTransaction.objects.filter(organisation=org).last()
    if last_tran:
        balance = last_tran.balance
    else:
        if text:
            balance = "Nil"
        else:
            balance = 0.0

    return balance
