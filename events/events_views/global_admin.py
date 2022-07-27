from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone

from accounts.models import User
from events.events_views.core import events_status_summary
from events.forms import CongressMasterForm
from events.models import (
    CongressMaster,
    BasketItem,
    EventEntry,
    EventEntryPlayer,
    Session,
)
from masterpoints.views import user_summary
from rbac.core import (
    rbac_user_has_role,
    rbac_get_users_with_role,
    rbac_group_id_from_name,
)
from rbac.decorators import rbac_check_role
from rbac.views import rbac_forbidden


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
            event_entry__event__congress__start_date__gte=timezone.now()
        )
        .filter(payment_type="my-system-dollars")
        .exclude(payment_status__in=["Paid", "Free"])
        .select_related("event_entry__event")
    )

    # Finished Congresses with pending bridge credits
    very_old_bridge_credit_entries = [
        old_bridge_credit_entry
        for old_bridge_credit_entry in old_bridge_credit_entries
        if old_bridge_credit_entry.event_entry.event.congress.end_date
        > timezone.now().date()
    ]

    return render(
        request,
        "events/global_admin/global_admin_event_payment_health_report.html",
        {
            "events": events,
            "basket_items_with_paid_entries": basket_items_with_paid_entries,
            "old_bridge_credit_entries": old_bridge_credit_entries,
            "very_old_bridge_credit_entries": very_old_bridge_credit_entries,
        },
    )
