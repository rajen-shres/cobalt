from django.shortcuts import render, get_object_or_404
from events.models import Congress, CongressMaster
from organisations.decorators import check_club_menu_access


@check_club_menu_access()
def congress_list_htmx(request, club):
    """show congress list for a given congress_master_id"""

    # We don't check if this user should have access as we only produce a list.
    # Downstream security will cover us if they try to do anything
    congress_master = get_object_or_404(
        CongressMaster, request.POST.get("congress_master_id")
    )
    congresses = Congress.objects.filter(congress_master=congress_master)

    return render(
        request,
        "organisations/club_menu/congress/congress_list_htmx.html",
        {
            "congress_master": congress_master,
            "congresses": congresses,
        },
    )
