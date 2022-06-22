import copy
import logging
import re
from datetime import timedelta

import pytz
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, escape
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods

from accounts.models import User
from cobalt.settings import (
    COBALT_HOSTNAME,
    SUMMERNOTE_CONFIG,
    RBAC_HELPDESK_GROUP,
    TIME_ZONE,
    ABF_USER,
    GLOBAL_TITLE,
)
from notifications.notifications_views.core import (
    send_cobalt_email_with_template,
    send_cobalt_email_preformatted,
)
from rbac.core import (
    rbac_get_users_with_role,
    rbac_add_user_to_group,
    rbac_get_group_by_name,
    rbac_remove_user_from_group,
)
from rbac.decorators import rbac_check_role
from support.forms import (
    IncidentForm,
    AttachmentForm,
    IncidentLineItemForm,
    NotifyUserByTypeForm,
)
from support.models import Incident, IncidentLineItem, Attachment, NotifyUserByType

TZ = pytz.timezone(TIME_ZONE)

logger = logging.getLogger("cobalt")


def _get_user_details_from_ticket(ticket):
    """internal function to get basic user information from the ticket"""
    if ticket.reported_by_user:  # registered
        first_name = ticket.reported_by_user.first_name
        email = ticket.reported_by_user.email
        full_name = ticket.reported_by_user.full_name
    else:  # not registered
        first_name = ticket.reported_by_name.split(" ")[0]
        email = ticket.reported_by_email
        full_name = ticket.reported_by_name

    return first_name, email, full_name


def _email_table(ticket, full_name):
    """format the details of the ticket for use in emails"""

    owner = ticket.assigned_to.full_name if ticket.assigned_to else "Unassigned"

    created_date_local = ticket.created_date.astimezone(TZ)

    return f"""<br><br><table class="receipt" border="1" cellpadding="0" cellspacing="0">
                    <tr>
                        <td style='text-align: left'><b>Ticket #{ticket.id}</b>
                        <td style='text-align: left'>{ticket.title}
                    </tr>
                    <tr>
                        <td style='text-align: left'><b>Member</b>
                        <td style='text-align: left'>{full_name}
                    </tr>
                    <tr>
                        <td style='text-align: left'><b>Status</b>
                        <td style='text-align: left'>{ticket.status}
                    </tr>
                    <tr>
                        <td style='text-align: left'><b>Type</b>
                        <td style='text-align: left'>{ticket.incident_type}
                    </tr>
                    <tr>
                        <td style='text-align: left'><b>Created Date</b>
                        <td style='text-align: left'>{created_date_local:%Y-%m-%d %H:%M}
                    </tr>
                    <tr>
                        <td style='text-align: left'><b>Assigned To</b>
                        <td style='text-align: left'>{owner}
                    </tr>
                    <tr>
                        <td style='text-align: left' colspan="2">{ticket.description}
                    </tr>
                </table><br><br>
            """


def _notify_user_common(ticket, subject, email_ticket_msg, email_ticket_footer=""):
    """Common parts of notifying a user"""

    first_name, email, full_name = _get_user_details_from_ticket(ticket)
    email_table = _email_table(ticket, full_name)
    email_body = f"""{email_ticket_msg}{email_table}{email_ticket_footer}"""
    link = reverse("support:helpdesk_user_edit", kwargs={"ticket_id": ticket.id})
    additional_words = mark_safe(
        f"<br><i><span style='color: #778899;'>{GLOBAL_TITLE} support hours are 9-5 Monday to Friday (excluding public holidays).</i></span>"
    )

    context = {
        "box_colour": "warn",
        "name": first_name,
        "title": subject,
        "host": COBALT_HOSTNAME,
        "link_text": "Open Ticket",
        "link": link,
        "email_body": email_body,
        "additional_words": additional_words,
    }

    send_cobalt_email_with_template(to_address=email, context=context)


def notify_user_new_ticket_by_form(request, ticket):
    """Notify a user when a new ticket is raised through the form - ie they did it themselves"""

    subject = f"Support Ticket Raised #{ticket.id}"
    email_ticket_msg = "We have created a support ticket for you."
    email_ticket_footer = (
        "You will be notified via email when the status of this ticket changes.<br><br>"
    )

    _notify_user_common(ticket, subject, email_ticket_msg, email_ticket_footer)


def _notify_user_new_ticket_by_staff(staff_name, ticket):
    """Notify a user when a new ticket is raised by staff"""

    subject = f"Support Ticket Raised #{ticket.id}"
    email_ticket_msg = f"{staff_name} has created a support ticket for you."
    email_ticket_footer = (
        "You will be notified via email when the status of this ticket changes.<br><br>"
    )

    _notify_user_common(ticket, subject, email_ticket_msg, email_ticket_footer)


def _notify_user_updated_ticket(request, ticket, comment):
    """Notify a user when a ticket is updated"""

    subject = f"Support Ticket Updated #{ticket.id}"
    email_ticket_msg = f"{request.user.full_name} has updated a support ticket for you."
    email_ticket_footer = f"""<h2>Last Comment</h2>{comment}<br><br>
        You will be notified via email when the status of this ticket changes.<br><br>"""

    _notify_user_common(ticket, subject, email_ticket_msg, email_ticket_footer)


def _notify_user_reopened_ticket(request, ticket):
    """Notify a user when a ticket is reopened"""

    subject = f"Support Ticket Re-opened #{ticket.id}"
    email_ticket_msg = (
        f"{request.user.full_name} has re-opened a support ticket for you."
    )
    email_ticket_footer = "<br><br>You will be notified via email when the status of this ticket changes.<br><br>"

    _notify_user_common(ticket, subject, email_ticket_msg, email_ticket_footer)


def _notify_user_resolved_ticket(request, ticket, text):
    """Notify a user when a ticket is resolved"""

    last_part = f"<h2>Last Comment</h2>{text}"

    subject = "Support Ticket Closed"
    email_ticket_msg = f"{request.user.full_name} has closed a support ticket for you."
    email_ticket_footer = f"""<table class="receipt" border="1" cellpadding="0" cellspacing="0">
                        <tr>
                            <td style='text-align: left'><b>Latest Update</b>
                            <td style='text-align: left'>{last_part}
                        </tr>
                    </table>
                    <br><br>
                    Please contact us again if you are still having issues.
                    <br><br>"""

    _notify_user_common(ticket, subject, email_ticket_msg, email_ticket_footer)


def _notify_group_common(ticket, subject, email_ticket_msg, exclude=None):
    """Common shared code for notifying the group"""

    first_name, email, full_name = _get_user_details_from_ticket(ticket)
    email_table = _email_table(ticket, full_name)
    email_body = f"""{email_ticket_msg}{email_table}"""
    link = reverse("support:helpdesk_edit", kwargs={"ticket_id": ticket.id})

    # See who to send this to
    recipients = NotifyUserByType.objects.filter(
        incident_type__in=["All", ticket.incident_type]
    )

    for recipient in recipients:

        if recipient.staff == exclude:
            continue

        html_msg = render_to_string(
            "notifications/email_with_button.html",
            {
                "name": recipient.staff.first_name,
                "title": subject,
                "host": COBALT_HOSTNAME,
                "link_text": "Open Ticket",
                "link": link,
                "email_body": email_body,
            },
        )
        send_cobalt_email_preformatted(
            to_address=recipient.staff.email, subject=subject, msg=html_msg
        )


def notify_group_new_ticket(request, ticket):
    """Notify staff when a new ticket is raised"""

    first_name, email, full_name = _get_user_details_from_ticket(ticket)
    subject = f"Support Ticket Raised - Unassigned #{ticket.id}"
    email_ticket_msg = f"{full_name} has created a support ticket."

    _notify_group_common(ticket, subject, email_ticket_msg)


def notify_group_new_ticket_by_staff(staff_name, ticket, exclude=None):
    """Notify staff when a new ticket is raised by a staff member. Don't notify the person who raised it"""

    first_name, email, full_name = _get_user_details_from_ticket(ticket)
    subject = f"Support Ticket Raised - Unassigned #{ticket.id}"
    email_ticket_msg = f"{staff_name} has created a support ticket for {full_name}. This ticket is unassigned."

    _notify_group_common(ticket, subject, email_ticket_msg, exclude=exclude)


def _notify_group_update_to_unassigned_ticket(request, ticket, reply):
    """Notify staff when a user updates an unassigned ticket"""

    subject = f"Unassigned ticket updated by user #{ticket.id}"
    email_ticket_msg = (
        f"{request.user.full_name} has updated an unassigned support ticket:<br>{reply}"
    )

    _notify_group_common(ticket, subject, email_ticket_msg)


def _notify_group_user_closed_unassigned_ticket(request, ticket, reply):
    """Notify staff when a user closes an unassigned ticket"""

    subject = f"Unassigned ticket closed by user #{ticket.id}"
    email_ticket_msg = (
        f"{request.user.full_name} has closed an unassigned support ticket:<br>{reply}"
    )

    _notify_group_common(ticket, subject, email_ticket_msg)


def _notify_group_unassigned_ticket(request, ticket):
    """Notify staff when a ticket is unassigned (previously assigned)"""

    subject = f"Support Ticket Unassigned #{ticket.id}"
    email_ticket_msg = f"{request.user.full_name} has unassigned a support ticket."

    _notify_group_common(ticket, subject, email_ticket_msg)


def _notify_staff_common(
    ticket, subject, email_ticket_msg, email_ticket_footer="", first_name_override=None
):
    """common parts for notifying staff"""

    first_name, email, full_name = _get_user_details_from_ticket(ticket)

    staff_first_name = first_name_override or ticket.assigned_to.first_name
    email_table = _email_table(ticket, full_name)
    email_body = f"""{email_ticket_msg}{email_table}{email_ticket_footer}"""
    link = reverse("support:helpdesk_edit", kwargs={"ticket_id": ticket.id})

    context = {
        "box_colour": "danger",
        "name": staff_first_name,
        "title": subject,
        "host": COBALT_HOSTNAME,
        "link_text": "Open Ticket",
        "link": link,
        "email_body": email_body,
    }

    send_cobalt_email_with_template(
        to_address=ticket.assigned_to.email, context=context
    )


def _notify_staff_assigned_to_ticket(staff_name, ticket):
    """Notify a staff member when a ticket is assigned to them"""

    subject = f"Support Ticket Assigned to You - #{ticket.id}"
    email_ticket_msg = f"{staff_name} has assigned a support ticket to you."
    _notify_staff_common(ticket, subject, email_ticket_msg)


def _notify_staff_user_update_to_ticket(request, ticket, reply):
    """Notify a staff member when a ticket is updated by the user"""

    subject = f"Support Ticket Updated by User - #{ticket.id}"
    email_ticket_msg = (
        f"{request.user.full_name} has updated a support ticket assigned to you."
    )
    email_ticket_footer = f"{reply}"
    _notify_staff_common(ticket, subject, email_ticket_msg, email_ticket_footer)


def _notify_staff_user_closed_ticket(request, ticket, reply):
    """Notify a staff member when a ticket is closed by the user"""

    subject = f"Support Ticket Closed by User - #{ticket.id}"
    email_ticket_msg = (
        f"{request.user.full_name} has closed a support ticket assigned to you."
    )
    email_ticket_footer = f"{reply}"
    _notify_staff_common(ticket, subject, email_ticket_msg, email_ticket_footer)


def notify_staff_mention(request, ticket, reply, first_name):
    """Notify a staff member when a comment has mentioned them"""

    subject = f"You Were Mentioned in an Update to a Support Ticket - #{ticket.id}"
    email_ticket_msg = f"{request.user.full_name} mentioned you in this ticket."
    email_ticket_footer = reply
    _notify_staff_common(
        ticket,
        subject,
        email_ticket_msg,
        email_ticket_footer,
        first_name_override=first_name,
    )


@rbac_check_role("support.helpdesk.edit")
def create_ticket(request):
    """View to create a new ticket"""

    form = IncidentForm(request.POST or None)
    if form.is_valid():
        ticket = form.save()

        # Notify the user
        _notify_user_new_ticket_by_staff(request.user.full_name, ticket)

        # if unassigned, notify everyone
        if ticket.status == "Unassigned":
            notify_group_new_ticket_by_staff(
                request.user.full_name, ticket, exclude=request.user
            )

        else:
            IncidentLineItem(
                incident=ticket,
                description=f"{request.user.full_name} assigned ticket to {ticket.assigned_to.full_name}",
            ).save()

            # If assigned to someone else, notify them
            if ticket.assigned_to != request.user:
                _notify_staff_assigned_to_ticket(request.user.full_name, ticket)

        messages.success(
            request,
            "Ticket successfully added.",
            extra_tags="cobalt-message-success",
        )
        return redirect("support:helpdesk_edit", ticket_id=ticket.pk)

    return render(request, "support/helpdesk/create_ticket.html", {"form": form})


@rbac_check_role("support.helpdesk.edit")
def helpdesk_menu(request):
    """Main Dashboard for the helpdesk"""

    tickets = Incident.objects.exclude(status="Closed")
    open_tickets = tickets.count()
    unassigned_tickets = tickets.filter(assigned_to=None)
    assigned_to_you = tickets.filter(assigned_to=request.user)
    assigned_to_others = tickets.exclude(assigned_to=request.user).exclude(
        assigned_to=None
    )

    return render(
        request,
        "support/helpdesk/helpdesk_menu.html",
        {
            "open_tickets": open_tickets,
            "unassigned_tickets": unassigned_tickets,
            "assigned_to_you": assigned_to_you,
            "assigned_to_others": assigned_to_others,
        },
    )


@rbac_check_role("support.helpdesk.edit")
def helpdesk_list(request):
    """list tickets and search"""

    form_severity = request.GET.get("severity")
    form_days = request.GET.get("days")
    form_user = request.GET.get("user")
    form_assigned_to = request.GET.get("assigned_to")
    form_status = request.GET.get("status")
    form_incident_type = request.GET.get("incident_type")

    days = int(form_days) if form_days else 7

    if days == -1:  # no filter
        tickets = Incident.objects.all().order_by("-created_date")
    else:
        ref_date = timezone.now() - timedelta(days=days)
        tickets = Incident.objects.filter(created_date__gte=ref_date).order_by(
            "-created_date"
        )

    if form_severity not in ["All", None]:
        tickets = tickets.filter(severity=form_severity)

    if form_status not in ["All", None]:
        tickets = tickets.filter(status=form_status)

    if form_user not in ["All", None]:
        form_user = int(form_user)
        tickets = tickets.filter(reported_by_user__pk=form_user)

    if form_incident_type not in ["All", None]:
        tickets = tickets.filter(incident_type=form_incident_type)

    if form_assigned_to not in ["All", None]:
        form_assigned_to = int(form_assigned_to)
        tickets = tickets.filter(assigned_to__pk=form_assigned_to)

    # lists should be based upon other filters
    incident_types = tickets.values("incident_type").distinct().order_by()
    severities = tickets.values("severity").distinct().order_by()
    statuses = tickets.values("status").distinct().order_by()

    # Should be able to do this with querysets but it seems to always return ids not User objects
    unique_users = []
    assigned_tos = []
    for ticket in tickets:
        this_user = ticket.reported_by_user
        if this_user not in unique_users and this_user:
            unique_users.append(this_user)
        this_staff = ticket.assigned_to
        if this_staff not in assigned_tos and this_staff:
            assigned_tos.append(this_staff)

    # sort lists alphabetically
    unique_users.sort(key=lambda x: x.first_name)
    assigned_tos.sort(key=lambda x: x.first_name)

    return render(
        request,
        "support/helpdesk/list_tickets.html",
        {
            "things": tickets,
            "severities": severities,
            "statuses": statuses,
            "users": unique_users,
            "form_days": form_days,
            "form_severity": form_severity,
            "form_user": form_user,
            "form_assigned_to": form_assigned_to,
            "form_status": form_status,
            "form_incident_type": form_incident_type,
            "assigned_tos": assigned_tos,
            "incident_types": incident_types,
        },
    )


@rbac_check_role("support.helpdesk.edit")
def edit_ticket(request, ticket_id):
    """View to edit a ticket"""

    ticket = get_object_or_404(Incident, pk=ticket_id)

    # We need the original status later - use copy to copy the data and unlink
    original_status = copy.copy(ticket.status)

    if request.method == "POST":
        form = IncidentForm(request.POST, instance=ticket)
        if form.is_valid():

            # check for delete flag
            delete = request.POST.get("delete")
            if delete:
                # client side validation says delete it
                ticket.delete()
                messages.success(
                    request,
                    "Ticket deleted. Your mistakes have been hidden and nobody knows.",
                    extra_tags="cobalt-message-success",
                )
                return redirect("support:helpdesk_menu")

            # handle changes
            ticket = form.save()

            messages.success(
                request,
                "Ticket successfully updated.",
                extra_tags="cobalt-message-success",
            )

            # Can close by using the resolve button or by changing the status
            if "status" in form.changed_data and ticket.status == "Closed":
                _notify_user_resolved_ticket(request, ticket, "")

            # Check for ticket being re-opened
            if (
                "status" in form.changed_data
                and ticket.status != "Closed"
                and original_status == "Closed"
            ):
                _notify_user_reopened_ticket(request, ticket)
                IncidentLineItem(
                    incident=ticket,
                    description=f"{request.user.full_name} re-opened ticket",
                ).save()

            # Check for assignment
            if "assigned_to" in form.changed_data:
                if (
                    not ticket.assigned_to
                ):  # It has been unassigned. Notify staff but not user.
                    _notify_group_unassigned_ticket(request, ticket)
                    IncidentLineItem(
                        incident=ticket,
                        description=f"{request.user.full_name} unassigned ticket",
                    ).save()
                else:  # assigned to someone
                    if ticket.assigned_to != request.user:  # Let them know
                        _notify_staff_assigned_to_ticket(request.user.full_name, ticket)
                    _notify_user_updated_ticket(
                        request,
                        ticket,
                        f"{ticket.assigned_to.full_name} has been assigned your ticket.",
                    )
                    IncidentLineItem(
                        incident=ticket,
                        description=f"{request.user.full_name} assigned ticket to {ticket.assigned_to.full_name}",
                    ).save()
        else:
            print(form.errors)

    form = IncidentForm(instance=ticket)
    comment_form = IncidentLineItemForm(auto_id="comment_%s")

    # get related items
    incident_line_items = IncidentLineItem.objects.filter(incident=ticket)
    attachments = Attachment.objects.filter(incident=ticket).order_by("-pk")

    first_name, _, _ = _get_user_details_from_ticket(ticket)

    staff_list = rbac_get_users_with_role("support.helpdesk.edit")

    staff = "".join(
        "'%s-%s', "
        % (
            escape(staff_list_item.first_name),
            escape(staff_list_item.last_name),
        )
        for staff_list_item in staff_list
    )
    if len(staff) > 0:
        staff = staff[:-2]

    staff = mark_safe(staff)

    return render(
        request,
        "support/helpdesk/edit_ticket.html",
        {
            "form": form,
            "comment_form": comment_form,
            "user": ticket.reported_by_user,
            "ticket": ticket,
            "incident_line_items": incident_line_items,
            "first_name": first_name,
            "attachments": attachments,
            "staff": staff,
        },
    )


@rbac_check_role("support.helpdesk.edit")
@require_http_methods(["POST"])
def add_comment(request, ticket_id):
    """Form to add a comment. Form is embedded in the edit_ticket page"""

    ticket = get_object_or_404(Incident, pk=ticket_id)

    form = IncidentLineItemForm(request.POST, auto_id="comment_%s")

    # If this isn't assigned then assign it now
    if not ticket.assigned_to:
        ticket.assigned_to = request.user
        ticket.status = "In Progress"
        ticket.save()

    # get private flag
    private = request.POST.get("private")
    comment_type = "Private" if private else "Default"

    if form.is_valid():
        text = form.cleaned_data["description"]
        action = form.cleaned_data["action"]

        # See if we are also closing the ticket
        and_close = action in ["add-close", "add-close-silent"]

        # See if we are also changing status to awaiting user feedback
        and_awaiting = action == "add-awaiting"

        # add comment
        IncidentLineItem(
            description=text,
            staff=request.user,
            incident=ticket,
            comment_type=comment_type,
        ).save()

        # look for mentions in the text e.g. @Betty-Bunting

        staff_list = rbac_get_users_with_role("support.helpdesk.edit")

        for staff in staff_list:
            if f"@{staff.first_name}-{staff.last_name}" in text:
                notify_staff_mention(request, ticket, text, staff.first_name)

        if and_awaiting:
            IncidentLineItem(
                description="Changed status to Awaiting User Feedback",
                staff=request.user,
                incident=ticket,
            ).save()
            ticket.status = "Pending User Feedback"
            ticket.save()

        if and_close:
            IncidentLineItem(
                description="Closed ticket", staff=request.user, incident=ticket
            ).save()
            ticket.status = "Closed"
            ticket.save()

            if private:
                text = ""

            if action != "add-close-silent":
                _notify_user_resolved_ticket(request, ticket, text)
                msg = "Ticket closed and user notified."
            else:
                msg = "Ticket closed, user NOT notified."

            messages.success(
                request,
                msg,
                extra_tags="cobalt-message-success",
            )
            return redirect("support:helpdesk_menu")

        else:
            if private:
                messages.success(
                    request,
                    "Ticket updated with private message.",
                    extra_tags="cobalt-message-success",
                )
            else:
                messages.success(
                    request,
                    "Ticket updated and user notified.",
                    extra_tags="cobalt-message-success",
                )
                _notify_user_updated_ticket(request, ticket, text)

    return redirect("support:helpdesk_edit", ticket_id=ticket_id)


@rbac_check_role("support.helpdesk.edit")
def helpdesk_attachments(request, ticket_id):
    """Manage attachments"""

    ticket = get_object_or_404(Incident, pk=ticket_id)

    if request.method == "POST":
        form = AttachmentForm(request.POST, request.FILES)

        if form.is_valid():
            attachment = form.save()
            IncidentLineItem(
                incident=ticket,
                staff=request.user,
                description=f"Added attachment {attachment.description}",
            ).save()
            messages.success(
                request, "Attachment added", extra_tags="cobalt-message-success"
            )
            return redirect("support:helpdesk_edit", ticket_id=ticket_id)

    else:
        form = AttachmentForm()

    # Get attachments
    attachments = Attachment.objects.filter(incident=ticket).order_by("-pk")

    return render(
        request,
        "support/helpdesk/attachments.html",
        {"form": form, "ticket": ticket, "attachments": attachments},
    )


@rbac_check_role("support.helpdesk.edit")
def helpdesk_delete_attachment_ajax(request):
    """Ajax call to delete an attachment from an incident"""

    if request.method == "GET":
        attachment_id = request.GET["attachment_id"]

        attachment = get_object_or_404(Attachment, pk=attachment_id)

        IncidentLineItem(
            incident=attachment.incident,
            staff=request.user,
            description=f"Deleted attachment {attachment.description}",
        ).save()

        attachment.delete()

        response_data = {"message": "Success"}
        return JsonResponse({"data": response_data})


@login_required()
def user_edit_ticket(request, ticket_id):
    """Page for a user to see their ticket"""

    ticket = get_object_or_404(Incident, pk=ticket_id)

    # check access
    if ticket.reported_by_user != request.user:
        return HttpResponse("Access denied.")

    if request.method == "POST":
        reply = request.POST.get(
            "reply", ""
        )  # let them post a blank reply if they like

        # update to ticket by user
        if "reply_button" in request.POST:

            IncidentLineItem(
                incident=ticket, description=reply, staff=request.user
            ).save()

            if ticket.status == "Unassigned":
                _notify_group_update_to_unassigned_ticket(request, ticket, reply)
            else:
                _notify_staff_user_update_to_ticket(request, ticket, reply)

            messages.success(
                request,
                "Ticket successfully updated and notifications sent.",
                extra_tags="cobalt-message-success",
            )

        # Close button - No name comes through as the JS to confirm loses it
        else:

            reply = f"{request.user.full_name} closed this ticket\n\n{reply}"

            IncidentLineItem(
                incident=ticket, description=reply, staff=request.user
            ).save()

            if ticket.status == "Unassigned":
                _notify_group_user_closed_unassigned_ticket(request, ticket, reply)
            else:
                _notify_staff_user_closed_ticket(request, ticket, reply)

            ticket.status = "Closed"
            ticket.save()

            messages.success(
                request,
                "Ticket successfully closed and notifications sent.",
                extra_tags="cobalt-message-success",
            )
    # get related items
    incident_line_items = IncidentLineItem.objects.filter(incident=ticket).exclude(
        comment_type="Private"
    )

    return render(
        request,
        "support/helpdesk/user_edit_ticket.html",
        {
            "ticket": ticket,
            "incident_line_items": incident_line_items,
        },
    )


def get_tickets(user):
    """get open tickets - called by the context_processors in cobalt"""

    return Incident.objects.filter(reported_by_user=user).exists()


@login_required()
def user_list_tickets(request):
    """Allow a user to view their tickets"""

    open_tickets = (
        Incident.objects.exclude(status="Closed")
        .filter(reported_by_user=request.user)
        .order_by("-created_date")
    )
    closed_tickets = (
        Incident.objects.filter(status="Closed")
        .filter(reported_by_user=request.user)
        .order_by("-created_date")
    )

    return render(
        request,
        "support/helpdesk/user_list_tickets.html",
        {
            "open_tickets": open_tickets,
            "closed_tickets": closed_tickets,
        },
    )


@rbac_check_role("support.helpdesk.edit")
def helpdesk_admin(request, notify_form=None):
    """Basic User admin for the helpdesk module. helpdesk_admin_add_notify calls us with the form if it has an error
    otherwise the errors aren't returned to the user"""

    notify_user_by_types = NotifyUserByType.objects.all()
    staff = rbac_get_users_with_role("support.helpdesk.edit")
    if not notify_form:
        notify_form = NotifyUserByTypeForm()

    return render(
        request,
        "support/helpdesk/helpdesk_admin.html",
        {
            "notify_user_by_types": notify_user_by_types,
            "staff": staff,
            "notify_form": notify_form,
        },
    )


@rbac_check_role("support.helpdesk.edit")
def helpdesk_admin_add_notify(request):
    """add a user and notify type to table"""

    form = NotifyUserByTypeForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request,
            "Notification successfully added.",
            extra_tags="cobalt-message-success",
        )
    else:
        print(form.errors)

    return helpdesk_admin(request, form)


@rbac_check_role("support.helpdesk.edit")
def helpdesk_delete_notify_ajax(request):
    """Ajax call to delete a notify user record"""

    if request.method == "GET":
        notify_id = request.GET["notify_id"]

        notify = get_object_or_404(NotifyUserByType, pk=notify_id)

        notify.delete()

        response_data = {"message": "Success"}
        return JsonResponse({"data": response_data})


@rbac_check_role("support.helpdesk.edit")
def helpdesk_admin_add_staff(request):
    """add a helpdesk user"""

    if request.method == "POST":
        staff_id = request.POST.get("staff_user")
        staff = get_object_or_404(User, pk=staff_id)

        group = rbac_get_group_by_name(RBAC_HELPDESK_GROUP)
        rbac_add_user_to_group(staff, group)

        messages.success(
            request,
            "User successfully added.",
            extra_tags="cobalt-message-success",
        )

    return redirect("support:helpdesk_admin")


@rbac_check_role("support.helpdesk.edit")
def helpdesk_delete_staff_ajax(request):
    """Ajax call to delete helpdesk user"""

    if request.method == "GET":

        if len(rbac_get_users_with_role("support.helpdesk.edit")) == 1:
            response_data = {
                "message": "Error. Cannot delete the last person from this group"
            }
            return JsonResponse({"data": response_data})

        staff_id = request.GET["staff_id"]

        staff = get_object_or_404(User, pk=staff_id)
        group = rbac_get_group_by_name(RBAC_HELPDESK_GROUP)

        rbac_remove_user_from_group(staff, group)

        response_data = {"message": "Success"}
        return JsonResponse({"data": response_data})


def create_ticket_api(
    title,
    description=None,
    reported_by_user: User = None,
    status="Unassigned",
    severity="Medium",
    incident_type="Other",
    assigned_to=None,
):
    """API for other parts of the system to raise a ticket"""

    if not reported_by_user:
        reported_by_user = User.objects.get(pk=ABF_USER)

    ticket = Incident(
        reported_by_user=reported_by_user,
        title=title,
        description=description,
        severity=severity,
        incident_type=incident_type,
        assigned_to=assigned_to,
        status=status,
    )

    ticket.save()

    # IncidentLineItem(
    #     incident=ticket,
    #     description="Ticket raised by the system.",
    # ).save()

    # Notify the user if there is one
    if reported_by_user.id != ABF_USER:
        _notify_user_new_ticket_by_staff("The System", ticket)

    # Notify the assignee if there is one
    if assigned_to:
        _notify_staff_assigned_to_ticket("The System", ticket)

    # if unassigned, notify everyone
    if ticket.status == "Unassigned":
        notify_group_new_ticket_by_staff("The System", ticket)


def close_old_tickets():
    """Called from cron via a management command to close any tickets over 30 days old with no activity"""

    logger.info("Looking for old tickets to close")

    # Get date 30 days ago
    ref_date = timezone.now() - timedelta(days=30)

    # Get tickets which are in progress or waiting for user feedback which haven't have any action for 30 days or more
    inactive_tickets = Incident.objects.filter(
        incidentlineitem__created_date__lt=ref_date
    ).filter(status__in=["In Progress", "Pending User Feedback"])

    if not inactive_tickets:
        logger.info("No tickets are old enough to close")
        return

    system_account = User.objects.get(pk=ABF_USER)

    for inactive_ticket in inactive_tickets:
        logger.info(f"Closing ticket {inactive_ticket}")
        IncidentLineItem(
            incident=inactive_ticket,
            staff=system_account,
            description="Ticket automatically closed after 30 days of inactivity",
        ).save()
        inactive_ticket.status = "Closed"
        inactive_ticket.save()
