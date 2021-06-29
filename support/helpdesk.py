from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from rbac.decorators import rbac_check_role
from support.forms import IncidentForm, AttachmentForm
from support.models import Incident, IncidentLineItem, Attachment


@rbac_check_role("support.helpdesk.edit")
def create_ticket(request):
    """ View to create a new ticket """

    form = IncidentForm(request.POST or None)
    if form.is_valid():
        ticket = form.save()
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
    """ View to edit a new ticket """

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
                messages.success(
                    request,
                    "Ticket closed and user notified.",
                    extra_tags="cobalt-message-success",
                )
                return redirect("support:helpdesk_menu")

            form.save()
            messages.success(
                request,
                "Ticket successfully updated.",
                extra_tags="cobalt-message-success",
            )
        else:
            print(form.errors)

    form = IncidentForm(instance=ticket)

    # get related items
    incident_line_items = IncidentLineItem.objects.filter(incident=ticket)
    attachments = Attachment.objects.filter(incident=ticket).order_by("-pk")

    if ticket.reported_by_user:
        first_name = ticket.reported_by_user.first_name
    else:
        first_name = ticket.reported_by_name.split(" ")[0]

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
            messages.success(request, "Attachment added", extra_tags="cobalt-message-success")
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

