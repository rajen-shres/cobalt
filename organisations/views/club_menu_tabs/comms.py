from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse

from organisations.decorators import check_club_menu_access
from organisations.forms import TagForm
from organisations.models import ClubTag, MemberClubTag


@check_club_menu_access()
def email_htmx(request, club):
    """build the comms email tab in club menu"""

    return render(
        request,
        "organisations/club_menu/comms/email_htmx.html",
        {"club": club},
    )


@check_club_menu_access()
def email_send_htmx(request, club):
    """send an email"""

    return render(
        request,
        "organisations/club_menu/comms/email_send_htmx.html",
        {"club": club},
    )


@check_club_menu_access()
def tags_htmx(request, club):
    """build the comms tags tab in club menu"""

    if "add" in request.POST:
        form = TagForm(request.POST)

        if form.is_valid():
            ClubTag.objects.get_or_create(
                organisation=club, tag_name=form.cleaned_data["tag_name"]
            )

    form = TagForm()

    tags = (
        ClubTag.objects.prefetch_related("memberclubtag_set")
        .filter(organisation=club)
        .order_by("tag_name")
    )

    # Add on count of how many members have this tag
    for tag in tags:
        uses = MemberClubTag.objects.filter(club_tag=tag).count()
        tag.uses = uses
        tag.hx_post = reverse("organisations:club_menu_tab_comms_tags_delete_tag_htmx")
        tag.hx_vars = f"club_id:{club.id},tag_id:{tag.id}"

    return render(
        request,
        "organisations/club_menu/comms/tags_htmx.html",
        {"club": club, "tags": tags, "form": form},
    )


@check_club_menu_access()
def delete_tag_htmx(request, club):
    """Delete a tag"""

    tag_id = request.POST.get("tag_id")
    tag = get_object_or_404(ClubTag, pk=tag_id)
    if tag.organisation == club:
        tag.delete()

    return tags_htmx(request)


@check_club_menu_access()
def tags_add_user_tag(request, club):
    """Add a tag to a user"""

    tag_id = request.POST.get("tag_id")
    tag = get_object_or_404(ClubTag, pk=tag_id)
    system_number = request.POST.get("system_number")

    if tag.organisation == club:
        MemberClubTag(club_tag=tag, system_number=system_number).save()
        return HttpResponse("Tag Added")

    return HttpResponse("Error")


@check_club_menu_access()
def tags_remove_user_tag(request, club):
    """Remove a tag from a user"""

    tag_id = request.POST.get("tag_id")
    tag = get_object_or_404(ClubTag, pk=tag_id)
    system_number = request.POST.get("system_number")

    if tag.organisation == club:
        member_tag = MemberClubTag.objects.filter(
            club_tag=tag, system_number=system_number
        )
        member_tag.delete()
        return HttpResponse("Tag Removed")

    return HttpResponse("Error")


@check_club_menu_access()
def public_info_htmx(request, club):
    """build the comms public info tab in club menu"""

    return render(
        request,
        "organisations/club_menu/comms/public_info_htmx.html",
        {"club": club},
    )
