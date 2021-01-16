from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.template.loader import render_to_string
from django.db.models import Sum, Q
from .models import (
    Congress,
    Category,
    CongressMaster,
    Event,
    Session,
    EventEntry,
    EventEntryPlayer,
    PAYMENT_TYPES,
    BasketItem,
    EventLog,
    EventPlayerDiscount,
    EVENT_PLAYER_FORMAT_SIZE,
    Bulletin,
    PartnershipDesk,
    CongressDownload,
)
from accounts.models import User, TeamMate
from notifications.views import contact_member

# from .core import basket_amt_total, basket_amt_paid, basket_amt_this_user_only, basket_amt_owing_this_user_only
from .forms import CongressForm, NewCongressForm, EventForm, SessionForm
from rbac.core import (
    rbac_user_allowed_for_model,
    rbac_get_users_with_role,
)
from rbac.views import rbac_user_has_role, rbac_forbidden

from payments.core import (
    payment_api,
    org_balance,
    update_account,
    update_organisation,
    get_balance,
)
from organisations.models import Organisation
from django.contrib import messages
import uuid
from .core import notify_conveners
from cobalt.settings import TBA_PLAYER, COBALT_HOSTNAME, BRIDGE_CREDITS
import json


@login_required()
def get_conveners_ajax(request, org_id):
    """ returns a list of conveners as html for an organisation """

    conveners = rbac_get_users_with_role("events.org.%s.edit" % org_id)

    ret = "<ul>"
    for con in conveners:
        ret += "<li>%s" % con
    ret += (
        "</ul><p>These can be changed from the <a href='/organisations/edit/%s' target='_blank'>Organisation Administration Page</p>"
        % org_id
    )

    data_dict = {"data": ret}
    return JsonResponse(data=data_dict, safe=False)


@login_required()
def get_congress_master_ajax(request, org_id):
    """ returns a list of congress_masters as html for an organisation """

    org = get_object_or_404(Organisation, pk=org_id)

    qs = CongressMaster.objects.filter(org=org).distinct("name")

    ret = "<option value=''>-----------"
    for cm in qs:
        ret += f"<option value='{cm.pk}'>{cm.name}</option>"

    data_dict = {"data": ret}
    return JsonResponse(data=data_dict, safe=False)


@login_required()
def get_congress_ajax(request, congress_id):
    """ returns a list of congresses as html for an congress_master """

    master = get_object_or_404(CongressMaster, pk=congress_id)

    qs = Congress.objects.filter(congress_master=master).distinct("name")

    ret = "<option value=''>-----------"
    for cm in qs:
        ret += f"<option value='{cm.id}'>{cm.name}</option>"

    data_dict = {"data": ret}
    return JsonResponse(data=data_dict, safe=False)


@login_required()
def delete_event_ajax(request):
    """ Ajax call to delete an event from a congress """

    if request.method == "GET":
        event_id = request.GET["event_id"]

    event = get_object_or_404(Event, pk=event_id)

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    event.delete()

    response_data = {}
    response_data["message"] = "Success"
    return JsonResponse({"data": response_data})


@login_required()
def delete_category_ajax(request):
    """ Ajax call to delete a category from an event """

    if request.method == "GET":
        category_id = request.GET["category_id"]

    category = get_object_or_404(Category, pk=category_id)

    # check access
    role = "events.org.%s.edit" % category.event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    category.delete()

    response_data = {}
    response_data["message"] = "Success"
    return JsonResponse({"data": response_data})


@login_required()
def delete_session_ajax(request):
    """ Ajax call to delete a session from a congress """

    if request.method == "GET":
        session_id = request.GET["session_id"]

    session = get_object_or_404(Session, pk=session_id)

    # check access
    role = "events.org.%s.edit" % session.event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    session.delete()

    response_data = {}
    response_data["message"] = "Success"
    return JsonResponse({"data": response_data})


@login_required()
def fee_for_user_ajax(request):
    """ Ajax call to get entry fee for a user in an event """

    if request.method == "GET":
        event_id = request.GET["event_id"]
        user_id = request.GET["user_id"]

    event = get_object_or_404(Event, pk=event_id)
    user = get_object_or_404(User, pk=user_id)

    entry_fee, discount, reason, description = event.entry_fee_for(user)

    response_data = {
        "entry_fee": entry_fee,
        "description": description,
        "discount": discount,
    }

    response_data["message"] = "Success"
    return JsonResponse({"data": response_data})


@login_required()
def payment_options_for_user_ajax(request):
    """Ajax call to get payment methods - basically team mate relationships

    We turn on this option if the other user has allowed the logged in user
    to make payments for them AND they either have auto top up enabled OR
    enough funds taking away events they have already entered but not paid for.
    This could be with ANY user as the person entering.

    e.g. Fred is entering with Bob as his partner. Bob has allowed Fred to
    do this but doesn't have auto top up enabled. Bob has $100 in his account
    and this event will cost $20. Fred already has another event in his
    basket with Bob as his partner for $50. Jane is also entering an event
    with Bob and has $20 for Bob to pay in her basket. Bob's current total
    commitment is $70, so the $20 for this event is okay. If this event was
    $31 then it would fail."""

    if request.method == "GET":
        entering_user_id = request.GET["entering_user_id"]
        other_user_id = request.GET["other_user_id"]
        event_id = request.GET["event_id"]

    # default to no
    reply = False
    response_data = {}

    # check if allowed to use funds
    user = get_object_or_404(User, pk=other_user_id)
    entrant = get_object_or_404(User, pk=entering_user_id)
    allowed = TeamMate.objects.filter(
        user=user, team_mate=entrant, make_payments=True
    ).exists()

    # check if auto topup enabled

    if allowed:
        if user.stripe_auto_confirmed == "On":
            reply = True
        else:

            # check if sufficient balance

            user_balance = get_balance(user)
            user_committed = 0.0
            event = get_object_or_404(Event, pk=event_id)
            entry_fee, discount, reason, description = event.entry_fee_for(user)

            # get all events with user committed
            basket_items = BasketItem.objects.all()
            for basket_item in basket_items:
                already = basket_item.event_entry.evententryplayer_set.filter(
                    player=user
                ).aggregate(Sum("entry_fee"))
                if already["entry_fee__sum"]:  # ignore None response
                    user_committed += float(already["entry_fee__sum"])

            if user_balance - user_committed - float(entry_fee) >= 0.0:
                reply = True
            else:
                if user_committed > 0.0:
                    response_data[
                        "description"
                    ] = f"{user.first_name} has insufficient funds taking into account other pending event entries."
                else:
                    response_data[
                        "description"
                    ] = f"{user.first_name} has insufficient funds."

    if reply:
        response_data["add_entry"] = "their-system-dollars"
        response_data["message"] = "Allowed"
    else:
        response_data["add_entry"] = ""
        response_data["message"] = "Blocked"

    return JsonResponse({"data": response_data})


@login_required()
def add_category_ajax(request):
    """ Ajax call to add an event category to an event """

    if request.method == "POST":
        event_id = request.POST["event_id"]
        text = request.POST["text"]

    event = get_object_or_404(Event, pk=event_id)

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    # add category
    category = Category(event=event, description=text)
    category.save()

    response_data = {}
    response_data["message"] = "Success"
    return JsonResponse({"data": response_data})


@login_required()
def admin_offsystem_pay_ajax(request):
    """ Ajax call to mark an off-system payment as made """

    if request.method == "POST":
        event_entry_player_id = request.POST["event_entry_player_id"]

    event_entry_player = get_object_or_404(EventEntryPlayer, pk=event_entry_player_id)

    # check access
    role = (
        "events.org.%s.edit"
        % event_entry_player.event_entry.event.congress.congress_master.org.id
    )
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    # Mark as paid
    event_entry_player.payment_status = "Paid"
    event_entry_player.payment_received = event_entry_player.entry_fee
    # TODO: client side screen to capture who actually paid this so don't need to assume it was the player
    event_entry_player.paid_by = event_entry_player.player
    event_entry_player.save()

    # Log it
    EventLog(
        event=event_entry_player.event_entry.event,
        actor=request.user,
        action=f"Marked {event_entry_player.player} as paid",
        event_entry=event_entry_player.event_entry,
    ).save()

    # Check if parent complete
    event_entry_player.event_entry.check_if_paid()

    response_data = {}
    response_data["message"] = "Success"
    return JsonResponse({"data": response_data})


@login_required()
def admin_offsystem_unpay_ajax(request):
    """ Ajax call to mark an off-system payment as no longer paid """

    if request.method == "POST":
        event_entry_player_id = request.POST["event_entry_player_id"]

    event_entry_player = get_object_or_404(EventEntryPlayer, pk=event_entry_player_id)

    # check access
    role = (
        "events.org.%s.edit"
        % event_entry_player.event_entry.event.congress.congress_master.org.id
    )
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    # Mark as unpaid
    event_entry_player.payment_status = "Unpaid"
    event_entry_player.payment_received = 0
    event_entry_player.save()

    # Log it
    EventLog(
        event=event_entry_player.event_entry.event,
        actor=request.user,
        action=f"Marked {event_entry_player.player} as unpaid",
        event_entry=event_entry_player.event_entry,
    ).save()

    # Check if parent complete
    event_entry_player.event_entry.check_if_paid()

    response_data = {}
    response_data["message"] = "Success"
    return JsonResponse({"data": response_data})


@login_required()
def admin_offsystem_pay_pp_ajax(request):
    """ Ajax call to mark a pp payment as paid """

    if request.method == "POST":
        event_entry_player_id = request.POST["event_entry_player_id"]

    event_entry_player = get_object_or_404(EventEntryPlayer, pk=event_entry_player_id)

    # check access
    role = (
        "events.org.%s.edit"
        % event_entry_player.event_entry.event.congress.congress_master.org.id
    )
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    # Mark as paid
    event_entry_player.payment_status = "Paid"
    event_entry_player.payment_received = event_entry_player.entry_fee
    # TODO: client side screen to capture who actually paid this so don't need to assume it was the player
    event_entry_player.paid_by = event_entry_player.player
    event_entry_player.save()

    # Log it
    EventLog(
        event=event_entry_player.event_entry.event,
        actor=request.user,
        action=f"Marked {event_entry_player.player} as paid (pp)",
        event_entry=event_entry_player.event_entry,
    ).save()

    # Check if parent complete
    event_entry_player.event_entry.check_if_paid()

    response_data = {}
    response_data["message"] = "Success"
    return JsonResponse({"data": response_data})


@login_required()
def admin_offsystem_unpay_pp_ajax(request):
    """ Ajax call to mark a pp payment as no longer paid """

    if request.method == "POST":
        event_entry_player_id = request.POST["event_entry_player_id"]

    event_entry_player = get_object_or_404(EventEntryPlayer, pk=event_entry_player_id)

    # check access
    role = (
        "events.org.%s.edit"
        % event_entry_player.event_entry.event.congress.congress_master.org.id
    )
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    # Mark as unpaid
    event_entry_player.payment_status = "Unpaid"
    event_entry_player.payment_received = 0
    event_entry_player.save()

    # Log it
    EventLog(
        event=event_entry_player.event_entry.event,
        actor=request.user,
        action=f"Marked {event_entry_player.player} as unpaid (pp)",
        event_entry=event_entry_player.event_entry,
    ).save()

    # Check if parent complete
    event_entry_player.event_entry.check_if_paid()

    response_data = {}
    response_data["message"] = "Success"
    return JsonResponse({"data": response_data})


@login_required()
def delete_basket_item_ajax(request):
    """ Delete an item from a users basket (and delete the event entry) """

    if request.method == "GET":
        basket_id = request.GET["basket_id"]

    basket_item = get_object_or_404(BasketItem, pk=basket_id)

    if basket_item.player == request.user:
        basket_item.event_entry.delete()
        basket_item.delete()

        response_data = {"message": "Success"}
        return JsonResponse({"data": response_data})


@login_required()
def admin_player_discount_delete_ajax(request):
    """ Delete a player discount record """

    if request.method == "POST":
        discount_id = request.POST["event_player_discount_id"]

        event_player_discount = get_object_or_404(EventPlayerDiscount, pk=discount_id)

        # check access
        role = (
            "events.org.%s.edit"
            % event_player_discount.event.congress.congress_master.org.id
        )
        if not rbac_user_has_role(request.user, role):
            return rbac_forbidden(request, role)

        # Log it
        EventLog(
            event=event_player_discount.event,
            actor=request.user,
            action=f"Deleted Event Player Discount for {event_player_discount.player}",
        ).save()

        # Delete it
        event_player_discount.delete()

        response_data = {"message": "Success"}

    else:

        response_data = {"message": "Incorrect call"}

    return JsonResponse({"data": response_data})


@login_required()
def check_player_entry_ajax(request):
    """ Check if a player is already entered in an event """

    if request.method == "GET":
        member_id = request.GET["member_id"]
        event_id = request.GET["event_id"]

        member = get_object_or_404(User, pk=member_id)
        event = get_object_or_404(Event, pk=event_id)

        if member.id == TBA_PLAYER:
            return JsonResponse({"message": "Not Entered"})

        event_entry = (
            EventEntryPlayer.objects.filter(player=member)
            .filter(event_entry__event=event)
            .exclude(event_entry__entry_status="Cancelled")
            .count()
        )

        if event_entry:
            return JsonResponse({"message": "Already Entered"})
        else:
            return JsonResponse({"message": "Not Entered"})


@login_required()
def change_player_entry_ajax(request):
    """ Change a player in an event. Also update entry_fee if required """

    if request.method == "GET":
        member_id = request.GET["member_id"]
        event_entry_player_id = request.GET["player_event_entry"]

        member = get_object_or_404(User, pk=member_id)
        event_entry_player = get_object_or_404(
            EventEntryPlayer, pk=event_entry_player_id
        )
        event_entry = get_object_or_404(
            EventEntry, pk=event_entry_player.event_entry.id
        )
        event = get_object_or_404(Event, pk=event_entry.event.id)
        congress = get_object_or_404(Congress, pk=event.congress.id)

        # check access on the parent event_entry
        if not event_entry.user_can_change(request.user):
            return JsonResponse({"message": "Access Denied"})

        # update
        old_player = event_entry_player.player
        event_entry_player.player = member
        event_entry_player.save()

        # Log it
        EventLog(
            event=event,
            actor=request.user,
            event_entry=event_entry,
            action=f"Swapped {member} in for {old_player}",
        ).save()

        # notify both members
        context = {
            "name": event_entry_player.player.first_name,
            "title": "Event Entry - %s" % congress,
            "email_body": f"{request.user.full_name} has added you to {event}.<br><br>",
            "host": COBALT_HOSTNAME,
            "link": "/events/view",
            "link_text": "View Entry",
        }

        html_msg = render_to_string("notifications/email_with_button.html", context)

        # send
        contact_member(
            member=event_entry_player.player,
            msg="Entry to %s" % congress,
            contact_type="Email",
            html_msg=html_msg,
            link="/events/view",
            subject="Event Entry - %s" % congress,
        )

        context = {
            "name": old_player.first_name,
            "title": "Event Entry - %s" % congress,
            "email_body": f"{request.user.full_name} has removed you from {event}.<br><br>",
            "host": COBALT_HOSTNAME,
        }

        html_msg = render_to_string("notifications/email.html", context)

        # send
        contact_member(
            member=old_player,
            msg="Entry to %s" % congress,
            contact_type="Email",
            html_msg=html_msg,
            link="/events/view",
            subject="Event Entry - %s" % congress,
        )

        # tell the conveners
        email_msg = f"""{request.user.full_name} has changed an entry for {event.event_name} in {congress}.
                  <br><br>
                  <b>{old_player}</b> has been removed.
                  <br><br>
                  <b>{event_entry_player.player}</b> has been added.
                  <br><br>
                  """

        notify_conveners(
            congress=congress,
            event=event,
            subject=f"{event} - {event_entry_player.player} added to entry",
            email_msg=email_msg,
        )

        # Check entry fee - they can keep an early entry discount but nothing else
        #    original_entry_fee = event_entry_player.entry_fee

        # default value
        return_html = "Player successfully changed."

        # Check if this is a free entry - player 5 or 6
        if event_entry_player.payment_type == "Free":
            return JsonResponse({"message": "Success", "html": return_html})

        # get the entry fee based upon when the entry was created
        entry_fee, discount, reason, description = event.entry_fee_for(
            event_entry_player.player,
            event_entry_player.event_entry.first_created_date.date(),
        )

        event_entry_player.entry_fee = entry_fee
        event_entry_player.reason = reason
        event_entry_player.save()

        # adjust for over or under payment after player change

        difference = float(event_entry_player.payment_received) - float(
            event_entry_player.entry_fee
        )

        if difference > 0:  # overpaid
            # create payments in org account
            update_organisation(
                organisation=event_entry_player.event_entry.event.congress.congress_master.org,
                amount=-difference,
                description=f"{event_entry_player.event_entry.event.event_name} - {event_entry_player.paid_by} partial refund",
                source="Events",
                log_msg=event_entry_player.event_entry.event.event_name,
                sub_source="events_callback",
                payment_type="Refund",
                member=event_entry_player.paid_by,
            )

            # create payment for user
            update_account(
                member=event_entry_player.paid_by,
                amount=difference,
                description=f"Refund for {event_entry_player.event_entry.event.event_name} - {event_entry_player.player}",
                source="Events",
                sub_source="events_callback",
                payment_type="Refund",
                log_msg=event_entry_player.event_entry.event.event_name,
                organisation=event_entry_player.event_entry.event.congress.congress_master.org,
            )

            # update entry payment amount
            event_entry_player.payment_received = event_entry_player.entry_fee
            event_entry_player.save()

            return_html = f"Player successfully changed. A refund of {difference} credits was paid to {event_entry_player.paid_by}"

            # Log it
            EventLog(
                event=event,
                actor=request.user,
                event_entry=event_entry,
                action=f"Triggered refund for {member} - {difference} credits",
            ).save()

            # notify member of refund
            context = {
                "name": event_entry_player.paid_by.first_name,
                "title": "Refund from - %s" % event,
                "email_body": f"A refund of {difference} credits has been made to your {BRIDGE_CREDITS} accounts from {event}.<br><br>",
                "host": COBALT_HOSTNAME,
                "link": "/events/view",
                "link_text": "View Entry",
            }

            html_msg = render_to_string("notifications/email_with_button.html", context)

            # send
            contact_member(
                member=event_entry_player.paid_by,
                msg="Refund from - %s" % event,
                contact_type="Email",
                html_msg=html_msg,
                link="/events/view",
                subject="Refund from  %s" % event,
            )

            # tell the conveners
            msg = f"""{event_entry_player.paid_by.full_name} has been refunded
                      {difference} {BRIDGE_CREDITS} for {event.event_name} in {congress}
                      due to change of player from {old_player} to {event_entry_player.player}.
                      <br><br>
                      """
            notify_conveners(
                congress,
                event,
                f"{event} - {event_entry_player.paid_by} refund",
                msg,
            )

        # if money is owing then update paid status on event_entry
        if difference < 0:
            difference = -difference
            event_entry_player.payment_status = "Unpaid"
            event_entry_player.save()
            event_entry.check_if_paid()
            return_html = f"Player succesfully changed. There are {difference} credits required for this player entry."

        # Check if payment status should be paid. e.g. enter as Youth and swap to another, then back to Youth
        if event_entry_player.entry_fee == event_entry_player.payment_received:
            event_entry_player.payment_status = "Paid"
            event_entry_player.save()
            event_entry.check_if_paid()

        # the HTML screen reloads but we need to tell the user what happened first
        return JsonResponse({"message": "Success", "html": return_html})


@login_required()
def add_player_to_existing_entry_ajax(request):
    """ Add a player to a team from the edit entry screen """

    if request.method == "GET":
        event_entry_id = request.GET["event_entry_id"]
        event_entry = get_object_or_404(EventEntry, pk=event_entry_id)

        # check access
        if not event_entry.user_can_change(request.user):
            return JsonResponse({"message": "Access Denied"})

        # check if already full
        event_entry_player_count = (
            EventEntryPlayer.objects.filter(event_entry=event_entry)
            .exclude(event_entry__entry_status="Cancelled")
            .count()
        )

        if (
            event_entry_player_count
            >= EVENT_PLAYER_FORMAT_SIZE[event_entry.event.player_format]
        ):
            return JsonResponse({"message": "Maximum player number reached"})

        # if we got here everything is okay, create new player
        # this will always be the 5th or 6th player in a team and will be free
        event_entry_player = EventEntryPlayer()
        tba = get_object_or_404(User, pk=TBA_PLAYER)
        event_entry_player.player = tba
        event_entry_player.event_entry = event_entry
        event_entry_player.entry_fee = 0
        event_entry_player.payment_status = "Free"
        event_entry_player.payment_type = "Free"
        event_entry_player.save()

        # log it
        EventLog(
            event=event_entry.event,
            actor=request.user,
            action="Added a player",
            event_entry=event_entry,
        ).save()

        return JsonResponse({"message": "Success"})


@login_required()
def delete_player_from_entry_ajax(request):
    """ Delete a player (5 or 6 only) from a team from the edit entry screen """

    if request.method == "GET":
        event_entry_player_id = request.GET["event_entry_player_id"]
        event_entry_player = get_object_or_404(
            EventEntryPlayer, pk=event_entry_player_id
        )

        # check access
        if not event_entry_player.event_entry.user_can_change(request.user):
            return JsonResponse({"message": "Access Denied"})

        # check if extra player
        event_entry_player_count = (
            EventEntryPlayer.objects.filter(event_entry=event_entry_player.event_entry)
            .exclude(event_entry__entry_status="Cancelled")
            .count()
        )

        if event_entry_player_count < 5:
            return JsonResponse({"message": "Not an extra player. Cannot delete."})

        # log it
        EventLog(
            event=event_entry_player.event_entry.event,
            actor=request.user,
            action=f"Deleted {event_entry_player.player} from team",
            event_entry=event_entry_player.event_entry,
        ).save()

        # if we got here everything is okay
        event_entry_player.delete()

        if event_entry_player.player.id != TBA_PLAYER:

            event = event_entry_player.event_entry.event
            congress = event_entry_player.event_entry.event.congress

            # notify member
            context = {
                "name": event_entry_player.player.first_name,
                "title": "Removal from Team in %s" % event,
                "email_body": f"{request.user.full_name} has removed you from their team in {event}.<br><br>",
                "host": COBALT_HOSTNAME,
            }

            html_msg = render_to_string("notifications/email.html", context)

            # send
            contact_member(
                member=event_entry_player.player,
                msg="Removal from %s" % event,
                contact_type="Email",
                html_msg=html_msg,
                link="/events/view",
                subject="Removal from %s" % event,
            )

            # tell the conveners
            msg = f"""{event_entry_player.player.full_name} has been removed from the team
                      by {request.user.full_name} for {event.event_name} in {congress}.
                      <br><br>
                      The team is still complete.
                      <br><br>
                      """
            notify_conveners(
                congress,
                event,
                f"{event} - Extra player {event_entry_player.player} removed",
                msg,
            )

        return JsonResponse({"message": "Success"})


@login_required()
def change_category_on_existing_entry_ajax(request, event_entry_id, category_id):

    event_entry = get_object_or_404(EventEntry, pk=event_entry_id)
    category = get_object_or_404(Category, pk=category_id)

    if not event_entry.user_can_change(request.user):
        return JsonResponse({"message": "Access Denied"})

    # log it
    EventLog(
        event=event_entry.event,
        actor=request.user,
        action=f"Changed category to {category} from {event_entry.category}",
        event_entry=event_entry,
    ).save()

    event_entry.category = category
    event_entry.save()

    return JsonResponse({"message": "Success"})


@login_required()
def change_answer_on_existing_entry_ajax(request, event_entry_id, answer):
    """ Update the answer to the question on entry """

    event_entry = get_object_or_404(EventEntry, pk=event_entry_id)

    if not event_entry.user_can_change(request.user):
        return JsonResponse({"message": "Access Denied"})

    # log it
    EventLog(
        event=event_entry.event,
        actor=request.user,
        action=f"Changed answer to {answer} from {event_entry.free_format_answer}",
        event_entry=event_entry,
    ).save()

    event_entry.free_format_answer = answer
    event_entry.save()

    return JsonResponse({"message": "Success"})


@login_required()
def admin_delete_bulletin_ajax(request):
    """ Ajax call to delete a bulletin from a congress """

    if request.method == "GET":
        bulletin_id = request.GET["bulletin_id"]

    bulletin = get_object_or_404(Bulletin, pk=bulletin_id)

    # check access
    role = "events.org.%s.edit" % bulletin.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    bulletin.delete()

    response_data = {}
    response_data["message"] = "Success"
    return JsonResponse({"data": response_data})


@login_required()
def admin_delete_download_ajax(request):
    """ Ajax call to delete a download from a congress """

    if request.method == "GET":
        download_id = request.GET["download_id"]

    download = get_object_or_404(CongressDownload, pk=download_id)

    # check access
    role = "events.org.%s.edit" % download.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    download.delete()

    response_data = {}
    response_data["message"] = "Success"
    return JsonResponse({"data": response_data})


@login_required()
def delete_me_from_partnership_desk(request, event_id):
    """ delete this user from the partnership desk """

    event = get_object_or_404(Event, pk=event_id)

    partnership = (
        PartnershipDesk.objects.filter(player=request.user).filter(event=event).first()
    )

    if partnership:
        # Log it
        EventLog(
            event=event,
            actor=request.user,
            action="Deleted partnership desk listing",
        ).save()
        partnership.delete()

    response_data = {}
    response_data["message"] = "Success"
    return JsonResponse({"data": response_data})


@login_required()
def contact_partnership_desk_person_ajax(request):
    """ get in touch with someone who you want to play with from the partnership desk """

    if request.method == "GET":
        partnership_desk_id = request.GET["partnership_desk_id"]
        partnership_desk = get_object_or_404(PartnershipDesk, pk=partnership_desk_id)
        message = request.GET["message"]

        # Log it
        EventLog(
            event=partnership_desk.event,
            actor=request.user,
            action=f"Shared partnership desk details with {partnership_desk.player}",
        ).save()

        email_body = f"""{request.user} has responded to your partnership desk search.<br><br>
                        <h3>Message</h3>
                        {message}<br><br>
                        <h3>Details</h3>
                        Event: {partnership_desk.event}<br>
                        Email: <a href="mailto:{request.user.email}">{request.user.email}</a><br>
                        Phone: {request.user.mobile}<br><br>
        """

        context = {
            "name": partnership_desk.player.first_name,
            "title": "Partner Request",
            "email_body": email_body,
            "host": COBALT_HOSTNAME,
            "link": "/events/view",
            "link_text": "View Event",
        }

        html_msg = render_to_string("notifications/email_with_button.html", context)

        # send
        contact_member(
            member=partnership_desk.player,
            msg="Partnership Message from %s" % request.user.full_name,
            contact_type="Email",
            html_msg=html_msg,
            link="/events/view",
            subject="Partnership Message",
        )

    response_data = {}
    response_data["message"] = "Success"
    return JsonResponse({"data": response_data})


@login_required()
def change_payment_method_on_existing_entry_ajax(request):
    """ Ajax call from edit event entry screen to change payment method """

    if request.method == "GET":
        player_entry_id = request.GET["player_entry_id"]
        payment_method = request.GET["payment_method"]

        player_entry = get_object_or_404(EventEntryPlayer, pk=player_entry_id)

        # Check access
        if not player_entry.event_entry.user_can_change(request.user):
            return JsonResponse({"message": "Access Denied"})

        player_entry.payment_type = payment_method
        if payment_method in ["bank-transfer", "cash", "cheque"]:
            player_entry.payment_status = "Pending Manual"
        else:
            player_entry.payment_status = "Unpaid"

        player_entry.save()

        return JsonResponse({"message": "Success"})

    return JsonResponse({"message": "Invalid call"})


@login_required()
def admin_event_entry_notes_ajax(request):
    """ Ajax call from event entry screen to update notes """

    if request.method == "POST":
        data = json.loads(request.body.decode("utf-8"))
        event_entry_id = int(data["id"])
        notes = data["notes"]

        event_entry = get_object_or_404(EventEntry, pk=event_entry_id)

        # check access
        role = "events.org.%s.edit" % event_entry.event.congress.congress_master.org.id
        if not rbac_user_has_role(request.user, role):
            return rbac_forbidden(request, role)

        event_entry.notes = notes
        event_entry.save()

        return JsonResponse({"message": "Success"})

    return JsonResponse({"message": "Invalid call"})
