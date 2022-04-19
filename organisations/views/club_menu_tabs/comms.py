from itertools import chain

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from post_office.models import EmailTemplate

from accounts.models import User, UnregisteredUser
from cobalt.settings import COBALT_HOSTNAME
from notifications.forms import OrgEmailForm
from notifications.models import Snooper, EmailBatchRBAC, EmailAttachment
from notifications.notifications_views.core import (
    send_cobalt_email_with_template,
    create_rbac_batch_id,
)
from organisations.decorators import check_club_menu_access
from organisations.forms import TagMultiForm, FrontPageForm, EmailAttachmentForm
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


def _send_email_to_tags(request, club, tags, email_form, club_template, attachments):
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
            first_name=recipient["first_name"],
            email=email,
            email_form=email_form,
            batch_id=batch_id,
            club_template=club_template,
            attachments=attachments,
        )

    return f"Email queued to send to {len(combined_list)} recipients"


def _send_email_sub(
    first_name, email, email_form, batch_id=None, club_template=None, attachments=None
):
    """Send an email sub task

    Args:
        first_name(str): name of person to send to
        email(str): email address
        email_form: OrgEmailForm which user has just completed
        batch_id(BatchID): batch id if required
        club_template(OrgEmailTemplate): has banner, footer etc for club
        attachments(dict): dict of attachments ('filename', 'path-to-file')
    """

    context = {
        "name": first_name,
        "subject": email_form.cleaned_data["subject"],
        "title": email_form.cleaned_data["subject"],
        "email_body": email_form.cleaned_data["org_email_body"],
        "box_colour": "danger",
    }

    # Get the extra fields that could have been overridden by the user
    reply_to = email_form.cleaned_data["reply_to"]
    from_name = email_form.cleaned_data["from_name"]

    sender = f"{from_name}<donotreply@myabf.com.au>" if from_name else None

    if club_template:
        context["img_src"] = club_template.banner.url
        context["footer"] = club_template.footer

    send_cobalt_email_with_template(
        to_address=email,
        context=context,
        batch_id=batch_id,
        template="system - club",
        reply_to=reply_to,
        sender=sender,
        attachments=attachments,
    )


@check_club_menu_access()
def email_send_htmx(request, club):
    """send an email"""

    message = None

    # We either get "test" to send a test message, "send" to send it, or nothing to show the empty form.
    if "test" not in request.POST and "send" not in request.POST:
        email_form = OrgEmailForm(club=club)
        tag_form = TagMultiForm(club=club)
    else:
        email_form = OrgEmailForm(request.POST, club=club)
        tag_form = TagMultiForm(request.POST, club=club)
        if not (email_form.is_valid() and tag_form.is_valid()):
            return HttpResponse(
                f"""<span
                        class='text-danger font-weight-bold'
                        _='on load wait 5 seconds
                        then transition opacity to 0
                        over 2 seconds
                        then remove me'
                        >There is an error in the data. Please look through the tabs and correct it.
                        </span>
                        {email_form.errors}
                        {tag_form.errors}
                        """
            )

        # Load template once if possible
        if email_form.cleaned_data["template"]:
            template_id = email_form.cleaned_data["template"]
            club_template = get_object_or_404(OrgEmailTemplate, pk=template_id)
        else:
            club_template = None

        # Get any attachments and convert to Django post office expected format
        attachment_ids = request.POST.getlist("selected_attachments")
        attachments = {}
        if attachment_ids:
            attachments_objects = EmailAttachment.objects.filter(id__in=attachment_ids)
            for attachments_object in attachments_objects:
                attachments[
                    attachments_object.filename()
                ] = attachments_object.attachment.path

        if "test" in request.POST:
            _send_email_sub(
                first_name=request.user.first_name,
                email=request.user.email,
                email_form=email_form,
                club_template=club_template,
                attachments=attachments,
            )

            return HttpResponse(
                """<span
                                        class='text-primary font-weight-bold'
                                        _='on load wait 5 seconds
                                        then transition opacity to 0
                                        over 2 seconds
                                        then remove me'
                                        >Test email sent. Check your inbox.
                                        </span>"""
            )
        else:

            # convert tags from strings to ints
            send_tags = list(map(int, tag_form.cleaned_data["tags"]))

            message = _send_email_to_tags(
                request=request,
                club=club,
                tags=send_tags,
                email_form=email_form,
                club_template=club_template,
                attachments=attachments,
            )
            return email_htmx(request, message=message)

    # Get tags, we include an everyone tag inside the template
    tags = ClubTag.objects.filter(organisation=club).order_by("tag_name")

    # Get total members for the Everyone option and also to block sending if there are no members
    total_members = (
        MemberMembershipType.objects.active()
        .filter(membership_type__organisation=club)
        .distinct("system_number")
        .count()
    )
    tag_count = {"EVERYONE": total_members}
    empty_tags = []

    for tag in tags:
        this_count = (
            MemberClubTag.objects.filter(club_tag=tag).distinct("system_number").count()
        )
        tag_count[tag.tag_name] = this_count
        if this_count == 0:
            empty_tags.append(tag.id)

    # Fill reply_to and from_name with values from the first template if there is one
    first_template = (
        OrgEmailTemplate.objects.filter(organisation=club).order_by("pk").first()
    )
    if first_template:
        email_form.fields["from_name"].initial = first_template.from_name
        email_form.fields["reply_to"].initial = first_template.reply_to

    return render(
        request,
        "organisations/club_menu/comms/email_send_htmx.html",
        {
            "club": club,
            "email_form": email_form,
            "tag_form": tag_form,
            "tags": tags,
            "tag_count": tag_count,
            "message": message,
            "no_members": total_members == 0,
            "empty_tags": empty_tags,
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


@login_required()
def email_preview_htmx(request):
    """Preview an email as user creates it"""

    template_id = request.POST.get("template")
    if template_id:
        template = get_object_or_404(OrgEmailTemplate, pk=template_id)
        img_src = template.banner.url
    else:
        template = None
        img_src = "/media/email_banners/default_banner.jpg"
    title = request.POST.get("subject")
    email_body = request.POST.get("org_email_body")

    host = COBALT_HOSTNAME

    return render(
        request,
        "organisations/club_menu/comms/email_preview_htmx.html",
        {
            "template": template,
            "img_src": img_src,
            "host": host,
            "title": title,
            "email_body": email_body,
        },
    )


@check_club_menu_access()
def from_and_reply_to_htmx(request, club):
    """rebuild the from and reply_to fields in the send email form if the template changes"""

    template_id = request.POST.get("template")
    template = get_object_or_404(OrgEmailTemplate, pk=template_id)

    email_form = OrgEmailForm(club=club)

    email_form.fields["from_name"].initial = template.from_name
    email_form.fields["reply_to"].initial = template.reply_to

    return render(
        request,
        "organisations/club_menu/comms/email_send_from_and_reply_to_htmx.html",
        {"email_form": email_form},
    )


@check_club_menu_access()
def email_attachment_htmx(request, club):
    """Upload an email attachment"""

    # TODO: Move this to notifications and make it more generic - organisation or member

    email_attachments = EmailAttachment.objects.filter(organisation=club).order_by(
        "-pk"
    )[:50]

    # Add hx_vars for the delete function
    for email_attachment in email_attachments:
        email_attachment.hx_vars = (
            f"club_id:{club.id},email_attachment_id:{email_attachment.id}"
        )
        email_attachment.modal_id = f"del_attachment{email_attachment.id}"

    return render(
        request,
        "organisations/club_menu/comms/email_attachment_htmx.html",
        {"club": club, "email_attachments": email_attachments},
    )


def _email_attachment_list_htmx(request, club):
    """Shows just the list of attachments, called if we delete or add an attachment"""

    email_attachments = EmailAttachment.objects.filter(organisation=club).order_by(
        "-pk"
    )[:50]

    # Add hx_vars for the delete function
    for email_attachment in email_attachments:
        email_attachment.hx_vars = (
            f"club_id:{club.id},email_attachment_id:{email_attachment.id}"
        )
        email_attachment.modal_id = f"del_attachment{email_attachment.id}"

    return render(
        request,
        "organisations/club_menu/comms/email_attachment_list_htmx.html",
        {"club": club, "email_attachments": email_attachments},
    )


@check_club_menu_access()
def upload_new_email_attachment_htmx(request, club):
    """Upload a new email attachment for a club"""

    form = EmailAttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        email_attachment = form.save(commit=False)
        email_attachment.organisation = club
        email_attachment.save()

    return _email_attachment_list_htmx(request, club)


@check_club_menu_access()
def delete_email_attachment_htmx(request, club):
    """Delete an email attachment for a club"""

    email_attachment_id = request.POST.get("email_attachment_id")
    email_attachment = get_object_or_404(EmailAttachment, pk=email_attachment_id)

    if email_attachment.organisation != club:
        return HttpResponse("Access Denied")

    # Delete file
    email_attachment.attachment.delete(False)
    # Delete database object
    email_attachment.delete()

    return _email_attachment_list_htmx(request, club)
