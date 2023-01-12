from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from cobalt.settings import TBA_PLAYER
from events.views.core import (
    events_status_summary,
    get_completed_congresses_with_money_due,
)
from events.forms import CongressMasterForm
from events.models import (
    CongressMaster,
    BasketItem,
    EventEntry,
    EventEntryPlayer,
    EventLog,
)
from masterpoints.views import user_summary
from rbac.core import (
    rbac_user_has_role,
    rbac_get_users_with_role,
    rbac_group_id_from_name,
)
from rbac.decorators import rbac_check_role
from rbac.views import rbac_forbidden
from utils.utils import cobalt_paginator


@login_required()
def global_admin_congress_masters(request):
    """administration of congress masters"""

    role = "events.global.edit"
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    congress_masters = CongressMaster.objects.all()

    # Group congress_masters by state
    grouped_by_state = {}
    for congress_master in congress_masters:

        if congress_master.org.state in grouped_by_state:
            grouped_by_state[congress_master.org.state].append(congress_master)
        else:
            grouped_by_state[congress_master.org.state] = [congress_master]

    return render(
        request,
        "events/global_admin/global_admin_congress_masters.html",
        {"grouped_by_state": grouped_by_state},
    )


@login_required()
def global_admin_edit_congress_master(request, id):
    """edit congress masters"""

    role = "events.global.edit"
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    congress_master = get_object_or_404(CongressMaster, pk=id)
    org = congress_master.org

    form = CongressMasterForm(request.POST or None, instance=congress_master)
    # Get list of conveners direct from RBAC
    conveners = rbac_get_users_with_role("events.org.%s.edit" % org.id)

    # Get default group name if we can
    qualifier = "rbac.orgs.clubs.%s.%s" % (
        org.state.lower(),
        org.name.lower().replace(" ", "_"),
    )
    rbac_group_id = rbac_group_id_from_name(qualifier, "congresses")

    if request.method == "POST":
        if form.is_valid:
            form.save()
            messages.success(
                request, "Congress Master added", extra_tags="cobalt-message-success"
            )
            return redirect("events:global_admin_congress_masters")

    return render(
        request,
        "events/global_admin/global_admin_congress_master_edit.html",
        {
            "congress_master": congress_master,
            "form": form,
            "conveners": conveners,
            "rbac_group_id": rbac_group_id,
        },
    )


@login_required()
def global_admin_create_congress_master(request):
    """create congress master"""

    role = "events.global.edit"
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    form = CongressMasterForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid:
            form.save()
            messages.success(
                request, "Congress Master added", extra_tags="cobalt-message-success"
            )
            return redirect("events:global_admin_congress_masters")

    return render(
        request,
        "events/global_admin/global_admin_congress_master_create.html",
        {"form": form},
    )


@rbac_check_role("events.global.view")
def global_admin_view_player_entries(request, member_id):
    """Allow an admin to see entries for a player

    Args:
        member_id: member to look up
        request (HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    member = get_object_or_404(User, pk=member_id)
    summary = user_summary(member.system_number)

    # See if we should include all entries or just future ones
    show_all = request.GET.get("show_all", False)

    basket_items = BasketItem.objects.select_related(
        "event_entry", "event_entry__event"
    ).filter(player=member)

    event_entries = EventEntry.objects.select_related(
        "event", "event__congress"
    ).filter(evententryplayer__player=member)

    if not show_all:
        event_entries = event_entries.filter(
            event__congress__start_date__gte=timezone.now()
        )

    event_entries = event_entries.order_by("-pk")

    return render(
        request,
        "events/global_admin/global_admin_view_player_entries.html",
        {
            "profile": member,
            "summary": summary,
            "basket_items_this": basket_items,
            "event_entries": event_entries,
            "show_all": show_all,
        },
    )


@rbac_check_role("events.global.view")
def global_admin_event_payment_health_report(request):
    """Shows a basic health report across all events"""

    # Events summary
    events = events_status_summary()

    # basket items with paid entries - should never happen
    event_entries = EventEntry.objects.filter(
        evententryplayer__payment_status="Paid"
    ).values("id")

    basket_items_with_paid_entries = BasketItem.objects.filter(
        event_entry__in=event_entries
    )

    # Started Congresses with pending bridge credits

    old_bridge_credit_entries = (
        EventEntryPlayer.objects.filter(
            event_entry__event__congress__start_date__lte=timezone.now()
        )
        .filter(payment_type="my-system-dollars")
        .exclude(payment_status__in=["Paid", "Free"])
        .exclude(player_id=TBA_PLAYER)
        .exclude(event_entry__entry_status="Cancelled")
        .exclude(entry_fee=0)
        .select_related("event_entry__event")
        .order_by("player__first_name")
    )

    # Finished Congresses with pending bridge credits
    very_old_bridge_credit_entries = []
    for old_bridge_credit_entry in old_bridge_credit_entries:
        event_end_date = old_bridge_credit_entry.event_entry.event.end_date()
        # if not event_end_date:
        #     print("No end date for", old_bridge_credit_entry.event_entry.event)
        if event_end_date and event_end_date < timezone.now().date():
            very_old_bridge_credit_entries.append(old_bridge_credit_entry)

    # Finished event, pending bridge credits, and still in basket
    dangerous_entries = []
    for very_old_bridge_credit_entry in very_old_bridge_credit_entries:
        if BasketItem.objects.filter(
            event_entry=very_old_bridge_credit_entry.event_entry
        ).exists():
            dangerous_entries.append(very_old_bridge_credit_entry)

    # Summary values
    bad_congresses, _, _ = get_completed_congresses_with_money_due()

    return render(
        request,
        "events/global_admin/global_admin_event_payment_health_report.html",
        {
            "events": events,
            "basket_items_with_paid_entries": basket_items_with_paid_entries,
            "very_old_bridge_credit_entries": very_old_bridge_credit_entries,
            "dangerous_entries": dangerous_entries,
            "bad_congresses": bad_congresses,
        },
    )


@rbac_check_role("events.global.edit")
def events_activity_view(request):
    """Show activity on the events module"""

    return render(request, "events/global_admin/events_activity_view.html")


@rbac_check_role("events.global.edit")
def events_activity_view_logs_htmx(request):
    """Show activity on the events module - EventLogs"""

    events_logs_qs = EventLog.objects.order_by("-pk").select_related(
        "event", "event__congress", "event__congress__congress_master__org", "actor"
    )
    events_logs = cobalt_paginator(request, events_logs_qs, 15)
    hx_post = reverse("events:events_activity_view_logs_htmx")
    hx_target = "#event_log"

    return render(
        request,
        "events/global_admin/events_activity_view_logs_htmx.html",
        {"things": events_logs, "hx_post": hx_post, "hx_target": hx_target},
    )
