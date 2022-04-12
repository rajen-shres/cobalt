from itertools import chain

from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from post_office.models import EmailTemplate

from accounts.models import User, UnregisteredUser
from notifications.forms import OrgEmailForm
from notifications.models import Snooper, EmailBatchRBAC
from notifications.notifications_views.core import (
    send_cobalt_email_with_template,
    create_rbac_batch_id,
)
from organisations.decorators import check_club_menu_access
from organisations.forms import TagMultiForm, FrontPageForm
from organisations.models import (
    ClubTag,
    MemberClubTag,
    MemberMembershipType,
    MemberClubEmail,
    OrganisationFrontPage,
    OrgEmailTemplate,
)
from organisations.views.club_menu_tabs.settings import tags_htmx

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


def _send_email_to_tags(request, club, tags, email_form, club_template):
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

    if not combined_list:
        return "There are no recipients for this email"

    for recipient in combined_list:
        override = overrides.filter(system_number=recipient["system_number"]).first()
        if override:
            email = override["email"]
            print(f"overriding email address for {recipient['system_number']}")
        else:
            email = recipient["email"]

        _send_email_sub(
            recipient["first_name"], email, email_form, batch_id, club_template
        )

    return f"Email queued to send to {len(combined_list)} recipients"


def _send_email_sub(first_name, email, email_form, batch_id=None, club_template=None):
    """Send an email sub task

    Args:
        first_name(str): name of person to send to
        email(str): email address
        email_form: OrgEmailForm which user has just completed
        batch_id(BatchID): batch id if required
        club_template(OrgEmailTemplate): has banner, footer etc for club
    """

    context = {
        "name": first_name,
        "subject": email_form.cleaned_data["subject"],
        "title": email_form.cleaned_data["subject"],
        "email_body": email_form.cleaned_data["body"],
        "box_colour": "danger",
    }

    if club_template:
        context["img_src"] = club_template.banner.url
        context["footer"] = club_template.footer

    send_cobalt_email_with_template(
        to_address=email,
        context=context,
        batch_id=batch_id,
        template="system - club",
    )


@check_club_menu_access()
def email_send_htmx(request, club):
    """send an email"""

    message = None

    if "test" not in request.POST and "send" not in request.POST:
        email_form = OrgEmailForm(club=club)
        tag_form = TagMultiForm(club=club)
    else:
        email_form = OrgEmailForm(request.POST, club=club)
        tag_form = TagMultiForm(request.POST, club=club)
        print(email_form.errors)
        if email_form.is_valid() and tag_form.is_valid():

            # Load template once if possible
            if email_form.cleaned_data["template"]:
                template_id = email_form.cleaned_data["template"]
                club_template = get_object_or_404(OrgEmailTemplate, pk=template_id)
            else:
                club_template = None

            if "test" in request.POST:
                _send_email_sub(
                    first_name=request.user.first_name,
                    email=request.user.email,
                    email_form=email_form,
                    club_template=club_template,
                )

                message = "Test email sent. Check your inbox."
            else:

                # convert tags from strings to ints
                send_tags = list(map(int, tag_form.cleaned_data["tags"]))

                response = _send_email_to_tags(
                    request, club, send_tags, email_form, club_template
                )
                return HttpResponse(response)

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
            message = "Data saved"
        else:
            print(front_page_form.errors)

    else:
        front_page_form = FrontPageForm(instance=front_page)

    return render(
        request,
        "organisations/club_menu/comms/public_info_htmx.html",
        {
            "club": club,
            "front_page_form": front_page_form,
            "message": message,
            "front_page": front_page,
        },
    )
