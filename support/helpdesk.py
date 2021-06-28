from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone

from rbac.decorators import rbac_check_role
from support.forms import CreateTicket
from support.models import Incident


@rbac_check_role("support.helpdesk.edit")
def create_ticket(request):
    """ View to create a new ticket """

    form = CreateTicket(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(
            request,
            "Ticket successfully added.",
            extra_tags="cobalt-message-success",
        )
        return redirect("support:helpdesk_menu")

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
    form_type = request.GET.get("type")

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
        tickets = tickets.filter(reported_by_user__contains=form_user)

    # lists should be based upon other filters
    severities = tickets.values("severity").distinct().order_by()
    statuses = tickets.values("status").distinct().order_by()
    users = (
        tickets.exclude(reported_by_user=None)
        .values("reported_by_user")
        .distinct()
        .order_by()
    )

    return render(
        request,
        "support/list_tickets.html",
        {
            "things": tickets,
            "severities": severities,
            "statuses": statuses,
            "users": users,
            "form_days": form_days,
            "form_severity": form_severity,
            "form_user": form_user,
            "form_assigned_to": form_assigned_to,
            "form_status": form_status,
            "form_type": form_type,
        },
    )
