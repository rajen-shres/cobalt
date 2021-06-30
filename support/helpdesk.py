from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from cobalt.settings import COBALT_HOSTNAME
from notifications.views import send_cobalt_email, CobaltEmail
from rbac.decorators import rbac_check_role
from support.forms import IncidentForm, AttachmentForm
from support.models import Incident, IncidentLineItem, Attachment, NotifyUserByType


def _get_user_details_from_ticket(ticket):
    """ internal function to get basic user information from the ticket """
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
    """ format the details of the ticket for use in emails """

    owner = ticket.assigned_to.full_name if ticket.assigned_to else "Unassigned"

    return f"""<table class="receipt" border="1" cellpadding="0" cellspacing="0">
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
                        <td style='text-align: left'><b>Created Date</b>
                        <td style='text-align: left'>{ticket.created_date:%Y-%m-%d %H:%M}
                    </tr>
                    <tr>
                        <td style='text-align: left'><b>Assigned To</b>
                        <td style='text-align: left'>{owner}
                    </tr>
                    <tr>
                        <td style='text-align: left' colspan="2"><pre>{ticket.description}</pre>
                    </tr>
                </table><br><br>
            """


def _notify_user_new_ticket(request, ticket):
    """ Notify a user when a new ticket is raised """

    first_name, email, full_name = _get_user_details_from_ticket(ticket)
    subject = "Support Ticket Raised"
    email_table = _email_table(ticket, full_name)
    email_body = f"""{request.user.full_name} has created a support ticket for you.
                    {email_table}
                    You will be notified via email when the status of this ticket changes.
                    <br><br>"""

    html_msg = render_to_string(
        "notifications/email.html",
        {
            "name": first_name,
            "title": subject,
            "host": COBALT_HOSTNAME,
            "email_body": email_body,
        },
    )

    send_cobalt_email(email, subject, html_msg, member=ticket.reported_by_user)


def _notify_user_updated_ticket(request, ticket, comment):
    """ Notify a user when a ticket is updated """

    first_name, email, full_name = _get_user_details_from_ticket(ticket)
    subject = f"Support Ticket Updated #{ticket.id}"
    email_table = _email_table(ticket, full_name)
    email_body = f"""{request.user.full_name} has updated a support ticket for you.
                    {email_table}
                    <table class="receipt" border="1" cellpadding="0" cellspacing="0">
                        <tr>
                            <td style='text-align: left'><b>Latest Update</b>
                            <td style='text-align: left'>{comment}
                        </tr>
                    </table>
                    <br><br>"""

    html_msg = render_to_string(
        "notifications/email.html",
        {
            "name": first_name,
            "title": subject,
            "host": COBALT_HOSTNAME,
            "email_body": email_body,
        },
    )

    send_cobalt_email(email, subject, html_msg, member=ticket.reported_by_user)


def _notify_user_resolved_ticket(request, ticket):
    """ Notify a user when a ticket is resolved """

    last_comment = (
        IncidentLineItem.objects.filter(incident=ticket)
        .exclude(comment_type="Private")
        .order_by("-created_date")
        .first()
    )
    if last_comment:
        last_part = f"<h2>Last Comment</h2><pre>{last_comment.description}</pre>"
    else:
        last_part = ""

    first_name, email, full_name = _get_user_details_from_ticket(ticket)
    email_table = _email_table(ticket, full_name)
    subject = "Support Ticket Resolved"
    email_body = f"""{request.user.full_name} has closed a support ticket for you.
                    {email_table}
                    <table class="receipt" border="1" cellpadding="0" cellspacing="0">
                        <tr>
                            <td style='text-align: left'><b>Latest Update</b>
                            <td style='text-align: left'>{last_part}
                        </tr>
                    </table>
                    <br><br>
                    Please contact us again if you are still having issues.
                    <br><br>"""

    html_msg = render_to_string(
        "notifications/email.html",
        {
            "name": first_name,
            "title": subject,
            "host": COBALT_HOSTNAME,
            "email_body": email_body,
        },
    )

    send_cobalt_email(email, subject, html_msg, member=ticket.reported_by_user)


def _notify_group_common(request, ticket, subject, email_ticket_msg):
    """ Common shared code for notifying the group """

    first_name, email, full_name = _get_user_details_from_ticket(ticket)
    email_table = _email_table(ticket, full_name)
    email_body = f"""{email_ticket_msg}{email_table}"""
    link = reverse("support:helpdesk_edit", kwargs={"ticket_id": ticket.id})

    # See who to send this to
    recipients = NotifyUserByType.objects.filter(
        incident_type__in=["All", ticket.incident_type]
    )
    email_sender = CobaltEmail()

    for recipient in recipients:
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
        email_sender.queue_email(
            recipient.staff.email, subject, html_msg, member=recipient.staff
        )

    email_sender.send()


def _notify_group_new_ticket(request, ticket):
    """ Notify staff when a new ticket is raised """

    subject = f"Support Ticket Raised - Unassigned #{ticket.id}"
    email_ticket_msg = f"{request.user.full_name} has created a support ticket."

    _notify_group_common(request, ticket, subject, email_ticket_msg)


def _notify_group_unassigned_ticket(request, ticket):
    """ Notify staff when a ticket is unassigned (previously assigned) """

    subject = f"Support Ticket Unassigned #{ticket.id}"
    email_ticket_msg = f"{request.user.full_name} has unassigned a support ticket."

    _notify_group_common(request, ticket, subject, email_ticket_msg)


def _notify_staff_assigned_to_ticket(request, ticket):
    """ Notify a staff member when a ticket is assigned to them """

    first_name, email, full_name = _get_user_details_from_ticket(ticket)
    email_table = _email_table(ticket, full_name)
    subject = f"Support Ticket Assigned to You - #{ticket.id}"
    email_body = (
        f"{request.user.full_name} has assigned a support ticket to you.{email_table}"
    )
    link = reverse("support:helpdesk_edit", kwargs={"ticket_id": ticket.id})

    html_msg = render_to_string(
        "notifications/email_with_button.html",
        {
            "name": ticket.assigned_to.first_name,
            "title": subject,
            "host": COBALT_HOSTNAME,
            "link_text": "Open Ticket",
            "link": link,
            "email_body": email_body,
        },
    )

    send_cobalt_email(email, subject, html_msg, member=ticket.assigned_to)


@rbac_check_role("support.helpdesk.edit")
def create_ticket(request):
    """ View to create a new ticket """

    form = IncidentForm(request.POST or None)
    if form.is_valid():
        ticket = form.save()

        # Notify the user
        _notify_user_new_ticket(request, ticket)

        # if unassigned, notify everyone
        if ticket.status == "Unassigned":
            _notify_group_new_ticket(request, ticket)

        else:
            IncidentLineItem(
                incident=ticket,
                description=f"{request.user.full_name} assigned ticket to {ticket.assigned_to.full_name}",
            ).save()

            # If assigned to someone else, notify them
            if ticket.assigned_to != request.user:
                _notify_staff_assigned_to_ticket(request, ticket)

        messages.success(
            request,
            "Ticket successfully added.",
            extra_tags="cobalt-message-success",
        )
        return redirect("support:helpdesk_edit", ticket_id=ticket.pk)

    return render(request, "support/create_ticket.html", {"form": form})


@rbac_check_role("support.helpdesk.edit")
def helpdesk_menu(request):
    """ Main Dashboard for the helpdesk """

    tickets = Incident.objects.exclude(status="Closed")
    open_tickets = tickets.count()
    unassigned_tickets = tickets.filter(assigned_to=None).count()

    return render(
        request,
        "support/helpdesk_menu.html",
        {"open_tickets": open_tickets, "unassigned_tickets": unassigned_tickets},
    )


@rbac_check_role("support.helpdesk.edit")
def helpdesk_list(request):
    """ list tickets and search """

    form_severity = request.GET.get("severity")
    form_days = request.GET.get("days")
    form_user = request.GET.get("user")
    form_assigned_to = request.GET.get("assigned_to")
    form_status = request.GET.get("status")
    form_incident_type = request.GET.get("incident_type")

    days = int(form_days) if form_days else 7

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
        "support/list_tickets.html",
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
    """ View to edit a ticket """

    ticket = get_object_or_404(Incident, pk=ticket_id)

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

            # check for resolve flag
            resolve = request.POST.get("resolve")
            if resolve:
                # client side validation says close it
                ticket.status = "Closed"
                ticket.save()
                _notify_user_resolved_ticket(request, ticket)
                messages.success(
                    request,
                    "Ticket closed and user notified.",
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
                _notify_user_resolved_ticket(request, ticket)

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
                        _notify_staff_assigned_to_ticket(request, ticket)
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

    # get related items
    incident_line_items = IncidentLineItem.objects.filter(incident=ticket)
    attachments = Attachment.objects.filter(incident=ticket).order_by("-pk")

    first_name, _, _ = _get_user_details_from_ticket(ticket)

    return render(
        request,
        "support/edit_ticket.html",
        {
            "form": form,
            "user": ticket.reported_by_user,
            "ticket": ticket,
            "incident_line_items": incident_line_items,
            "first_name": first_name,
            "attachments": attachments,
        },
    )


@rbac_check_role("support.helpdesk.edit")
def add_incident_line_item_ajax(request):
    """ Ajax call to add a line item """

    if request.method != "POST":
        return
    ticket_id = request.POST.get("ticket_id")
    private_flag = request.POST.get("private_flag")
    private_flag = private_flag == "1"
    text = request.POST.get("text")

    ticket = get_object_or_404(Incident, pk=ticket_id)

    comment_type = "Private" if private_flag else "Default"
    IncidentLineItem(
        incident=ticket, description=text, staff=request.user, comment_type=comment_type
    ).save()

    if not private_flag:
        _notify_user_updated_ticket(request, ticket, text)

    response_data = {"message": "Success"}
    return JsonResponse({"data": response_data})


@rbac_check_role("support.helpdesk.edit")
def helpdesk_attachments(request, ticket_id):
    """ Manage attachments """

    ticket = get_object_or_404(Incident, pk=ticket_id)

    if request.method == "POST":
        form = AttachmentForm(request.POST, request.FILES)

        if form.is_valid():
            form.save()
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
        "support/attachments.html",
        {"form": form, "ticket": ticket, "attachments": attachments},
    )


@rbac_check_role("support.helpdesk.edit")
def helpdesk_delete_attachment_ajax(request):
    """ Ajax call to delete an attachment from an incident """

    if request.method == "GET":
        attachment_id = request.GET["attachment_id"]

        attachment = get_object_or_404(Attachment, pk=attachment_id)

        attachment.delete()

        response_data = {"message": "Success"}
        return JsonResponse({"data": response_data})
