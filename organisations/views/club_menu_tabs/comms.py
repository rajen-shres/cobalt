from itertools import chain

from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse

from accounts.models import User, UnregisteredUser
from notifications.forms import EmailForm
from notifications.models import Snooper, EmailBatchRBAC
from notifications.views import create_rbac_batch_id, send_cobalt_email_with_template
from organisations.decorators import check_club_menu_access
from organisations.forms import TagForm, TagMultiForm, FrontPageForm
from organisations.models import (
    ClubTag,
    MemberClubTag,
    MemberMembershipType,
    MemberClubEmail,
    OrganisationFrontPage,
)

from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden
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
        batch_id.number_sent = snoopers.count()
        first_snooper = snoopers.first()
        if first_snooper:
            batch_id.created = first_snooper.post_office_email.created
            batch_id.subject = first_snooper.post_office_email.context["subject"]

    things = cobalt_paginator(request, batch_ids)

    return render(
        request,
        "organisations/club_menu/comms/email_htmx.html",
        {"club": club, "message": message, "things": things},
    )


def _send_email_to_tags(request, club, tags, email_form):
    """Send an email to a group of members identified by tags"""

    # let anyone with comms access to this org view them
    batch_id = create_rbac_batch_id(
        rbac_role=f"notifications.orgcomms.{club.id}.view",
        user=request.user,
        organisation=club,
    )

    # Check for Tag=0, means everyone
    if 0 in tags:
        tag_system_numbers = (
            MemberMembershipType.objects.active()
            .filter(membership_type__organisation=club)
            .distinct("system_number")
            .values("system_number")
        )
    else:
        tag_system_numbers = (
            MemberClubTag.objects.filter(club_tag__in=tags)
            .distinct("system_number")
            .values("system_number")
            # go through list of tags and create list of recipients, members could be in multiple tags
        )
    # Get real members
    members = User.objects.filter(system_number__in=tag_system_numbers).values(
        "email", "first_name", "system_number"
    )
    # Get unregistered TODO: handle club level emails
    un_regs = UnregisteredUser.objects.filter(
        system_number__in=tag_system_numbers
    ).values("email", "first_name", "system_number")

    # get club level email overrides
    overrides = MemberClubEmail.objects.filter(
        system_number__in=tag_system_numbers
    ).values("email", "system_number")

    combined_list = list(chain(members, un_regs))

    for recipient in combined_list:
        override = overrides.filter(system_number=recipient["system_number"]).first()
        if override:
            email = override["email"]
            print(f"overriding email address for {recipient['system_number']}")
        else:
            email = recipient["email"]
        _send_email_sub(request, recipient["first_name"], email, email_form, batch_id)


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
        tag_form = TagMultiForm(club=club)
    else:
        email_form = EmailForm(request.POST)
        tag_form = TagMultiForm(request.POST, club=club)
        print(tag_form.errors)
        if email_form.is_valid() and tag_form.is_valid():

            if "test" in request.POST:
                _send_email_sub(
                    request, request.user.first_name, request.user.email, email_form
                )
                message = "Test email sent. Check your inbox"
            else:

                # convert tags from strings to ints
                send_tags = list(map(int, tag_form.cleaned_data["tags"]))

                print(send_tags)

                _send_email_to_tags(request, club, send_tags, email_form)
                return HttpResponse(
                    "<h3>Email sent</h3>Click on Email to see sent messages."
                )

    # Get tags, we include an everyone tag inside the template
    tags = ClubTag.objects.filter(organisation=club)

    return render(
        request,
        "organisations/club_menu/comms/email_send_htmx.html",
        {
            "club": club,
            "email_form": email_form,
            "tag_form": tag_form,
            "tags": tags,
            "message": message,
        },
    )


@check_club_menu_access()
def email_view_htmx(request, club):
    """view an email"""

    batch_id = request.POST.get("batch_id")

    # Get the matching batch
    email_batch = EmailBatchRBAC.objects.prefetch_related(
        "batch_id__snooper_set__post_office_email"
    ).get(pk=batch_id)

    # We allow people with explicit access to see emails or global admins, not state admins
    if not (
        rbac_user_has_role(request.user, email_batch.rbac_role)
        or rbac_user_has_role(request.user, "orgs.admin.edit")
    ):
        return rbac_forbidden(request, email_batch.rbac_role)

    # Get the snoopers for this batch
    snoopers = Snooper.objects.select_related("post_office_email").filter(
        batch_id=email_batch.batch_id
    )

    # Get totals from the database
    db_totals = snoopers.aggregate(
        sent=Count("ses_sent_at"),
        delivered=Count("ses_delivered_at"),
        opened=Count("ses_last_opened_at"),
        clicked=Count("ses_last_clicked_at"),
        bounced=Count("ses_last_bounce_at"),
    )

    # Total count
    count = snoopers.count()

    # We only show the first email
    snooper = snoopers.first()

    totals = {}

    # Build dictionary of items from Snoopers - this is how the email got on after we sent it according to AWS SES
    for db_total in db_totals:
        line = {}
        line["name"] = db_total.split("_")[-1]
        line["amount"] = db_totals[db_total]
        line["percent"] = int(db_totals[db_total] * 100.0 / count)
        if line["percent"] == 100:
            line["colour"] = "success"
        elif line["percent"] >= 80:
            line["colour"] = "primary"
        elif line["percent"] >= 60:
            line["colour"] = "info"
        elif line["percent"] >= 40:
            line["colour"] = "warning"
        else:
            line["colour"] = "danger"
        # Bounces are always bad
        if line["name"] == "bounced":
            line["colour"] = "danger"
        totals[db_total] = line

    # Now build status of what Django Post Office knows
    po_counts = snoopers.aggregate(
        sent=Count("pk", filter=Q(post_office_email__status=0)),
        failed=Count("pk", filter=Q(post_office_email__status=1)),
        queued=Count("pk", filter=Q(post_office_email__status=2)),
        requeued=Count("pk", filter=Q(post_office_email__status=3)),
    )

    details = {
        "number_sent": count,
        "created": snooper.post_office_email.created,
        "subject": snooper.post_office_email.context["subject"],
        "totals": totals,
        "po_counts": po_counts,
    }

    return render(
        request,
        "organisations/club_menu/comms/email_view_htmx.html",
        {"club": club, "email_batch": email_batch, "details": details},
    )


@check_club_menu_access()
def tags_htmx(request, club):
    """build the comms tags tab in club menu"""

    if "add" in request.POST:
        form = TagForm(request.POST, club=club)

        if form.is_valid():
            ClubTag.objects.get_or_create(
                organisation=club, tag_name=form.cleaned_data["tag_name"]
            )
            # reset form
            form = TagForm(club=club)
    else:
        form = TagForm(club=club)

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

    front_page, _ = OrganisationFrontPage.objects.get_or_create(organisation=club)

    message = ""

    if "save" in request.POST:
        front_page_form = FrontPageForm(request.POST, instance=front_page)
        if front_page_form.is_valid():
            front_page_form.save()
            print("saved")
            message = "Data saved"
        else:
            print(front_page_form.errors)

    else:
        front_page_form = FrontPageForm(instance=front_page)

    return render(
        request,
        "organisations/club_menu/comms/public_info_htmx.html",
        {"club": club, "front_page_form": front_page_form, "message": message},
    )
