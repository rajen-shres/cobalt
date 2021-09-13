from itertools import chain

from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse

from accounts.models import User, UnregisteredUser
from notifications.forms import EmailForm
from notifications.models import Snooper, EmailBatchRBAC
from notifications.views import create_rbac_batch_id, send_cobalt_email_with_template
from organisations.decorators import check_club_menu_access
from organisations.forms import TagForm
from organisations.models import ClubTag, MemberClubTag
from post_office.models import Email as PostOfficeEmail

from utils.utils import cobalt_paginator


@check_club_menu_access()
def email_htmx(request, club, message=None):
    """build the comms email tab in club menu"""

    # Get the batch IDs for this club (and prefetch the other things we want)
    batch_ids = (
        EmailBatchRBAC.objects.prefetch_related(
            "batch_id__snooper_set__post_office_email"
        )
        .filter(rbac_role=f"notifications.orgcomms.{club.id}.view")
        .order_by("-pk")
    )

    # Augment data
    for batch_id in batch_ids:
        snoopers = Snooper.objects.filter(batch_id=batch_id.batch_id)
        first_snooper = snoopers.first()
        batch_id.created = first_snooper.post_office_email.created
        batch_id.number_sent = snoopers.count()
        batch_id.subject = first_snooper.post_office_email.context["subject"]

    things = cobalt_paginator(request, batch_ids, 4)

    return render(
        request,
        "organisations/club_menu/comms/email_htmx.html",
        {"club": club, "message": message, "things": things},
    )


def _send_email_to_tags(request, club, tags, email_form):
    """Send an email to a group of members identified by tags"""

    # let anyone with comms access to this org view them
    # TODO: Which group to use?
    batch_id = create_rbac_batch_id(f"notifications.orgcomms.{club.id}.view")

    # go through list of tags and create list of recipients, members could be in multiple tags
    tag_system_numbers = (
        MemberClubTag.objects.filter(club_tag__tag_name__in=tags)
        .distinct("system_number")
        .values("system_number")
    )
    # Get real members
    members = User.objects.filter(system_number__in=tag_system_numbers).values(
        "email", "first_name"
    )
    # Get unregistered TODO: handle club level emails
    un_regs = UnregisteredUser.objects.filter(
        system_number__in=tag_system_numbers
    ).values("email", "first_name")

    combined_list = list(chain(members, un_regs))

    for recipient in combined_list:
        _send_email_sub(
            request, recipient["first_name"], recipient["email"], email_form, batch_id
        )


def _send_email_sub(request, first_name, email, email_form, batch_id=None):
    """Send an email sub task"""

    context = {
        "name": first_name,
        "subject": email_form.cleaned_data["subject"],
        "title": f"From: {request.user}. This for , good on ya",
        "email_body": email_form.cleaned_data["body"],
        "link": "/events",
        "link_text": "click me",
        "box_colour": "danger",
    }

    send_cobalt_email_with_template(
        to_address=email,
        context=context,
        batch_id=batch_id,
    )


@check_club_menu_access()
def email_send_htmx(request, club):
    """send an email"""

    message = None

    if "test" not in request.POST and "send" not in request.POST:
        email_form = EmailForm()
    else:
        email_form = EmailForm(request.POST)
        if email_form.is_valid():
            if "test" in request.POST:
                _send_email_sub(
                    request, request.user.first_name, request.user.email, email_form
                )
                message = "Test email sent. Check your inbox"
            else:
                _send_email_to_tags(request, club, ["aaa"], email_form)
                return email_htmx(request, "Email sent")

    return render(
        request,
        "organisations/club_menu/comms/email_send_htmx.html",
        {"club": club, "email_form": email_form, "message": message},
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
