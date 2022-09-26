from django.shortcuts import get_object_or_404, render

from events.views.congress_builder import copy_congress_from_another
from events.models import CongressMaster, Congress
from organisations.decorators import check_club_menu_access
from organisations.views.club_menu import tab_congress_htmx
from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden


@check_club_menu_access()
def congress_list_htmx(request, club):
    """show congress list for a given congress_master_id"""

    # We don't check if this user should have access as we only produce a list.
    # Downstream security will cover us if they try to do anything

    congress_master = get_object_or_404(
        CongressMaster, pk=request.POST.get("congress_master_id")
    )
    congresses = Congress.objects.filter(congress_master=congress_master).order_by(
        "-pk"
    )

    return render(
        request,
        "organisations/club_menu/congress/congress_list_htmx.html",
        {
            "congress_master": congress_master,
            "congresses": congresses,
            "club": club,
        },
    )


@check_club_menu_access()
def create_series_htmx(request, club):
    """This returns the form to create a new series, we process the form in another URL as we want a different target.
    This just replaces the button, the submit replaces the whole section.
    """

    return render(
        request,
        "organisations/club_menu/congress/create_series_htmx.html",
        {"club": club},
    )


@check_club_menu_access()
def create_master_htmx(request, club):
    """This processes the form to create a new congress master"""

    # Check access (admin users can do this from the admin menu)
    role = f"events.org.{club.id}.edit"
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    name = request.POST.get("congress_master")
    CongressMaster(name=name, org=club).save()

    return tab_congress_htmx(request)


@check_club_menu_access()
def create_congress_htmx(request, club):

    # Check access (admin users can do this from the admin menu)
    role = f"events.org.{club.id}.edit"
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    congress_master = get_object_or_404(
        CongressMaster, pk=request.POST.get("congress_master_id")
    )
    Congress(congress_master=congress_master, name=congress_master.name).save()

    return congress_list_htmx(request)


@check_club_menu_access()
def copy_congress_htmx(request, club):

    # Check access (admin users can do this from the admin menu)
    role = f"events.org.{club.id}.edit"
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    congress_id = request.POST.get("congress_id")
    copy_congress_from_another(congress_id)
    return congress_list_htmx(request)


@check_club_menu_access()
def rename_series_form_htmx(request, club):
    """This returns the form to rename a series, we process the form in another URL as we want a different target.
    This just replaces the button, the submit replaces the whole section.
    """

    congress_master = get_object_or_404(
        CongressMaster, pk=request.POST.get("congress_master_id")
    )
    return render(
        request,
        "organisations/club_menu/congress/rename_series_htmx.html",
        {"club": club, "congress_master": congress_master},
    )


@check_club_menu_access()
def rename_series_htmx(request, club):
    """This returns the form to rename a series, we process the form in another URL as we want a different target.
    This just replaces the button, the submit replaces the whole section.
    """

    congress_master = get_object_or_404(
        CongressMaster, pk=request.POST.get("congress_master_id")
    )
    role = f"events.org.{congress_master.org.id}.edit"

    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    congress_master.name = request.POST.get("congress_master")
    congress_master.save()

    # return whole tab
    return tab_congress_htmx(request)


@check_club_menu_access()
def delete_congress_master_htmx(request, club):

    congress_master = get_object_or_404(
        CongressMaster, pk=request.POST.get("congress_master_id")
    )
    role = f"events.org.{congress_master.org.id}.edit"

    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if not Congress.objects.filter(congress_master=congress_master).exists():
        congress_master.delete()

    return tab_congress_htmx(request)
