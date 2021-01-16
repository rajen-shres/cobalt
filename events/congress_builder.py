""" This file contains all of the code relating to an convener building
    a congress or editing a congress. """

import csv
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.forms import formset_factory
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.utils import timezone, dateformat
from django.db.models import Sum, Q
from notifications.views import contact_member
from logs.views import log_event
from .models import (
    Congress,
    Category,
    CongressMaster,
    Event,
    Session,
    EventEntry,
    EventEntryPlayer,
    PAYMENT_TYPES,
    EVENT_PLAYER_FORMAT_SIZE,
    BasketItem,
    PlayerBatchId,
    EventLog,
    CongressDownload,
)
from accounts.models import User, TeamMate
from .forms import (
    CongressForm,
    NewCongressForm,
    EventForm,
    SessionForm,
    EventEntryPlayerForm,
    RefundForm,
    CongressDownloadForm,
)
from rbac.core import (
    rbac_user_allowed_for_model,
    rbac_get_users_with_role,
    rbac_user_has_role,
)
from rbac.views import rbac_forbidden
from .core import events_payments_callback
from payments.core import payment_api, org_balance, update_account, update_organisation
from organisations.models import Organisation
from django.contrib import messages
import uuid
from cobalt.settings import (
    GLOBAL_ORG,
    GLOBAL_CURRENCY_NAME,
    BRIDGE_CREDITS,
    TIME_ZONE,
    COBALT_HOSTNAME,
    TBA_PLAYER,
)
from datetime import datetime, date
import itertools
from utils.utils import cobalt_paginator
from django.utils.timezone import make_aware, now, utc
import pytz
from decimal import Decimal

TZ = pytz.timezone(TIME_ZONE)


@login_required()
def delete_congress(request, congress_id):
    """delete a congress

    Args:
        request(HTTPRequest): standard user request
        congress_id(int): congress to delete

    Returns:
        page(HTTPResponse): redirects to events
    """

    congress = get_object_or_404(Congress, pk=congress_id)

    # check access
    role = "events.org.%s.edit" % congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if request.method == "POST":

        congress.delete()
        messages.success(
            request, "Congress deleted", extra_tags="cobalt-message-success"
        )
        return redirect("events:events")

    return render(request, "events/delete_congress.html", {"congress": congress})


@login_required()
def create_congress_wizard(request, step=1, congress_id=None):
    """create a new congress using a wizard format.

    There are a number of steps. Step 1 creates a congress either from
    scratch or by copying another one. All other steps edit data on the
    congress. The last steps allows the congress to be published.

    """

    # handle stepper on screen
    step_list = {}
    for i in range(1, 8):
        step_list[i] = "btn-default"
    step_list[step] = "btn-primary"

    # Step 1 - Create
    if step == 1:
        return create_congress_wizard_1(request, step_list)

    # all subsequent steps need the congress
    congress = get_object_or_404(Congress, pk=congress_id)

    # check access
    role = "events.org.%s.edit" % congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if step == 2:
        return create_congress_wizard_2(request, step_list, congress)
    if step == 3:
        return create_congress_wizard_3(request, step_list, congress)
    if step == 4:
        return create_congress_wizard_4(request, step_list, congress)
    if step == 5:
        return create_congress_wizard_5(request, step_list, congress)
    if step == 6:
        return create_congress_wizard_6(request, step_list, congress)
    if step == 7:
        return create_congress_wizard_7(request, step_list, congress)


def create_congress_wizard_1(request, step_list):
    """ congress wizard step 1 - create """
    if request.method == "POST":

        form = NewCongressForm(request.POST)

        if form.is_valid():

            if "scratch" in request.POST:
                congress_master_id = form.cleaned_data["congress_master"]
                congress_master = get_object_or_404(
                    CongressMaster, pk=congress_master_id
                )

                # check access
                role = "events.org.%s.edit" % congress_master.org.id
                if not rbac_user_has_role(request.user, role):
                    return rbac_forbidden(request, role)

                congress = Congress()
                congress.congress_master = congress_master
                congress.save()
                messages.success(
                    request, "Congress Created", extra_tags="cobalt-message-success"
                )
                return redirect(
                    "events:create_congress_wizard", step=2, congress_id=congress.id
                )
            if "copy" in request.POST:
                congress_id = form.cleaned_data["congress"]
                congress = get_object_or_404(Congress, pk=congress_id)
                original_congress = get_object_or_404(Congress, pk=congress_id)
                congress.pk = None
                congress.save()

                # Also copy events and sessions
                events = Event.objects.filter(congress=original_congress)

                for event in events:
                    sessions = Session.objects.filter(event=event)
                    event.pk = None
                    event.congress = congress
                    event.save()
                    for session in sessions:
                        session.pk = None
                        session.event = event
                        session.save()

                messages.success(
                    request, "Congress Copied", extra_tags="cobalt-message-success"
                )
                return redirect(
                    "events:create_congress_wizard", step=2, congress_id=congress.id
                )

        else:
            print(form.errors)
    else:
        # valid orgs
        everything, valid_orgs = rbac_user_allowed_for_model(
            user=request.user, app="events", model="org", action="edit"
        )
        if everything:
            valid_orgs = Organisation.objects.all().values_list("pk")

        form = NewCongressForm(valid_orgs=valid_orgs)

        return render(
            request,
            "events/congress_wizard_1.html",
            {"form": form, "step_list": step_list},
        )


def create_congress_wizard_2(request, step_list, congress):
    """ wizard step 2 - general """

    if request.method == "POST":
        form = CongressForm(request.POST)
        if form.is_valid():
            congress.year = form.cleaned_data["year"]
            congress.name = form.cleaned_data["name"]
            congress.date_string = form.cleaned_data["date_string"]
            congress.start_date = form.cleaned_data["start_date"]
            congress.end_date = form.cleaned_data["end_date"]
            congress.general_info = form.cleaned_data["general_info"]
            congress.links = form.cleaned_data["links"]
            congress.people = form.cleaned_data["people"]
            congress.additional_info = form.cleaned_data["additional_info"]
            congress.save()
            return redirect(
                "events:create_congress_wizard", step=3, congress_id=congress.id
            )
        else:
            print(form.errors)
    else:
        # datepicker is very fussy about format
        initial = {}
        if congress.start_date:
            initial["start_date"] = congress.start_date.strftime("%d/%m/%Y")
        if congress.end_date:
            initial["end_date"] = congress.end_date.strftime("%d/%m/%Y")
        form = CongressForm(instance=congress, initial=initial)

    form.fields["year"].required = True
    form.fields["name"].required = True
    form.fields["start_date"].required = True
    form.fields["end_date"].required = True
    form.fields["date_string"].required = True
    form.fields["general_info"].required = True
    form.fields["links"].required = True
    form.fields["people"].required = True

    return render(
        request,
        "events/congress_wizard_2.html",
        {"form": form, "step_list": step_list, "congress": congress},
    )


def create_congress_wizard_3(request, step_list, congress):
    """ wizard step 3 - venue """

    if request.method == "POST":
        form = CongressForm(request.POST)
        if form.is_valid():
            congress.venue_name = form.cleaned_data["venue_name"]
            congress.venue_location = form.cleaned_data["venue_location"]
            congress.venue_transport = form.cleaned_data["venue_transport"]
            congress.venue_catering = form.cleaned_data["venue_catering"]
            congress.venue_additional_info = form.cleaned_data["venue_additional_info"]
            congress.venue_additional_info = form.cleaned_data["venue_additional_info"]
            congress.save()
            return redirect(
                "events:create_congress_wizard", step=4, congress_id=congress.id
            )
        else:
            print(form.errors)
    else:
        form = CongressForm(instance=congress)

    form.fields["venue_name"].required = True
    form.fields["venue_location"].required = True
    form.fields["venue_transport"].required = True
    form.fields["venue_catering"].required = True

    return render(
        request,
        "events/congress_wizard_3.html",
        {"form": form, "step_list": step_list, "congress": congress},
    )


def create_congress_wizard_4(request, step_list, congress):
    """ wizard step 3 - sponsor """

    if request.method == "POST":
        form = CongressForm(request.POST)
        if form.is_valid():
            congress.sponsors = form.cleaned_data["sponsors"]
            congress.save()
            return redirect(
                "events:create_congress_wizard", step=5, congress_id=congress.id
            )

        else:
            print(form.errors)
    else:
        form = CongressForm(instance=congress)

    return render(
        request,
        "events/congress_wizard_4.html",
        {"form": form, "step_list": step_list, "congress": congress},
    )


def create_congress_wizard_5(request, step_list, congress):
    """ wizard step 5 - options """

    if request.method == "POST":
        form = CongressForm(request.POST)
        if form.is_valid():
            congress.payment_method_system_dollars = form.cleaned_data[
                "payment_method_system_dollars"
            ]
            congress.payment_method_bank_transfer = form.cleaned_data[
                "payment_method_bank_transfer"
            ]
            congress.payment_method_cash = form.cleaned_data["payment_method_cash"]
            congress.payment_method_cheques = form.cleaned_data[
                "payment_method_cheques"
            ]
            congress.payment_method_off_system_pp = form.cleaned_data[
                "payment_method_off_system_pp"
            ]
            congress.entry_open_date = form.cleaned_data["entry_open_date"]
            congress.entry_close_date = form.cleaned_data["entry_close_date"]
            congress.automatic_refund_cutoff = form.cleaned_data[
                "automatic_refund_cutoff"
            ]
            congress.allow_partnership_desk = form.cleaned_data[
                "allow_partnership_desk"
            ]
            congress.allow_early_payment_discount = form.cleaned_data[
                "allow_early_payment_discount"
            ]
            congress.early_payment_discount_date = form.cleaned_data[
                "early_payment_discount_date"
            ]
            congress.allow_youth_payment_discount = form.cleaned_data[
                "allow_youth_payment_discount"
            ]
            congress.youth_payment_discount_date = form.cleaned_data[
                "youth_payment_discount_date"
            ]
            congress.senior_age = form.cleaned_data["senior_age"]
            congress.senior_date = form.cleaned_data["senior_date"]

            congress.bank_transfer_details = form.cleaned_data["bank_transfer_details"]
            congress.cheque_details = form.cleaned_data["cheque_details"]
            congress.save()
            return redirect(
                "events:create_congress_wizard", step=6, congress_id=congress.id
            )
        else:
            print(form.errors)

    else:
        # sort out dates
        initial = {}
        if congress.entry_open_date:
            initial["entry_open_date"] = congress.entry_open_date.strftime("%d/%m/%Y")
        if congress.automatic_refund_cutoff:
            initial[
                "automatic_refund_cutoff"
            ] = congress.automatic_refund_cutoff.strftime("%d/%m/%Y")
        if congress.entry_close_date:
            initial["entry_close_date"] = congress.entry_close_date.strftime("%d/%m/%Y")
        if congress.early_payment_discount_date:
            initial[
                "early_payment_discount_date"
            ] = congress.early_payment_discount_date.strftime("%d/%m/%Y")
        if congress.youth_payment_discount_date:
            initial[
                "youth_payment_discount_date"
            ] = congress.youth_payment_discount_date.strftime("%d/%m/%Y")
        if congress.senior_date:
            initial["senior_date"] = congress.senior_date.strftime("%d/%m/%Y")
        form = CongressForm(instance=congress, initial=initial)

    form.fields["payment_method_system_dollars"].required = True
    form.fields["payment_method_bank_transfer"].required = True
    form.fields["payment_method_cash"].required = True
    form.fields["payment_method_cheques"].required = True
    form.fields["payment_method_off_system_pp"].required = True
    form.fields["entry_open_date"].required = True
    form.fields["entry_close_date"].required = True
    form.fields["automatic_refund_cutoff"].required = True
    form.fields["allow_partnership_desk"].required = True
    form.fields["allow_early_payment_discount"].required = True
    form.fields["bank_transfer_details"].required = True
    form.fields["senior_date"].required = True
    form.fields["senior_age"].required = True
    form.fields["cheque_details"].required = True

    return render(
        request,
        "events/congress_wizard_5.html",
        {"form": form, "step_list": step_list, "congress": congress},
    )


def create_congress_wizard_6(request, step_list, congress):
    """ wizard step 6 - events """

    events = Event.objects.filter(congress=congress)

    if request.method == "POST":
        return redirect(
            "events:create_congress_wizard", step=7, congress_id=congress.id
        )

    # add start date and sort by start date
    events_list = {}
    events_list_sorted = {}
    for event in events:
        event.event_start_date = event.start_date()
        if event.event_start_date:
            events_list[event] = event.event_start_date
        else:
            events_list[event] = date(year=1967, month=5, day=3)
    print("\n\n\n")
    print(congress)
    print(events_list)
    print("\n\n\n")
    events_list_sorted = {
        key: value
        for key, value in sorted(events_list.items(), key=lambda item: item[1])
    }

    return render(
        request,
        "events/congress_wizard_6.html",
        {"step_list": step_list, "congress": congress, "events": events_list_sorted},
    )


def create_congress_wizard_7(request, step_list, congress):
    """ wizard step 7 - publish """

    if request.method == "POST":
        if "Publish" in request.POST:
            congress.status = "Published"
            congress.save()
            messages.success(
                request,
                "Congress published",
                extra_tags="cobalt-message-success",
            )
            return redirect("events:view_congress", congress_id=congress.id)

        if "Unpublish" in request.POST:
            congress.status = "Draft"
            congress.save()
            messages.success(
                request,
                "Congress returned to Draft status",
                extra_tags="cobalt-message-success",
            )

    url = "%s/%s/" % (reverse("events:create_congress_wizard"), congress.id)
    errors = []
    warnings = []

    if not congress.name:
        errors.append("<a href='%s%s'>%s</a>" % (url, 2, "Congress name is missing"))
    if not congress.additional_info:
        warnings.append(
            "<a href='%s%s'>%s</a>" % (url, 2, "Congress Additional Info is missing")
        )
    if not congress.start_date:
        errors.append("<a href='%s%s'>%s</a>" % (url, 2, "Start date is missing"))
    if not congress.end_date:
        errors.append("<a href='%s%s'>%s</a>" % (url, 2, "End date is missing"))
    if not congress.date_string:
        warnings.append("<a href='%s%s'>%s</a>" % (url, 2, "Date string is missing"))
    if not congress.year:
        warnings.append("<a href='%s%s'>%s</a>" % (url, 2, "Year is missing"))
    if not congress.general_info:
        errors.append("<a href='%s%s'>%s</a>" % (url, 2, "General is missing"))
    if not congress.people:
        errors.append("<a href='%s%s'>%s</a>" % (url, 2, "People is missing"))
    if not congress.venue_name:
        warnings.append("<a href='%s%s'>%s</a>" % (url, 3, "Venue name is missing"))
    if not congress.venue_location:
        warnings.append("<a href='%s%s'>%s</a>" % (url, 3, "Venue location is missing"))
    if not congress.venue_transport:
        warnings.append(
            "<a href='%s%s'>%s</a>" % (url, 3, "Venue transport is missing")
        )
    if not congress.venue_catering:
        warnings.append("<a href='%s%s'>%s</a>" % (url, 3, "Venue catering is missing"))
    if not congress.venue_additional_info:
        warnings.append(
            "<a href='%s%s'>%s</a>" % (url, 3, "Venue Additional info is missing")
        )
    if not congress.entry_open_date:
        warnings.append(
            "<a href='%s%s'>%s</a>"
            % (
                url,
                5,
                "Entry open date is missing. Entries will be accepted any time before closing date.",
            )
        )
    if not congress.entry_close_date:
        warnings.append(
            "<a href='%s%s'>%s</a>"
            % (
                url,
                5,
                "Entry close date is missing. Entries will be accepted even after the congress has started.",
            )
        )

    events = Event.objects.filter(congress=congress)
    if events.count() == 0:
        errors.append(
            "<a href='%s%s'>%s</a>" % (url, 6, "This congress has no events defined")
        )

    for event in events:
        sessions = Session.objects.filter(event=event).count()
        if sessions == 0:
            errors.append(
                "<a href='%s%s'>%s</a>"
                % (url, 6, f"{event.event_name} has no sessions defined")
            )

    return render(
        request,
        "events/congress_wizard_7.html",
        {
            "step_list": step_list,
            "congress": congress,
            "errors": errors,
            "warnings": warnings,
        },
    )


def _update_event(request, form, event, congress, msg):
    """ common shared function to update an event with form data """

    event.congress = congress
    event.event_name = form.cleaned_data["event_name"]
    event.description = form.cleaned_data["description"]
    event.max_entries = form.cleaned_data["max_entries"]
    event.event_type = form.cleaned_data["event_type"]
    event.entry_open_date = form.cleaned_data["entry_open_date"]
    event.entry_close_date = form.cleaned_data["entry_close_date"]
    event.player_format = form.cleaned_data["player_format"]
    event.entry_fee = form.cleaned_data["entry_fee"]
    event.entry_early_payment_discount = form.cleaned_data[
        "entry_early_payment_discount"
    ]
    event.entry_youth_payment_discount = form.cleaned_data[
        "entry_youth_payment_discount"
    ]
    event.save()
    messages.success(request, msg, extra_tags="cobalt-message-success")


@login_required
def create_event(request, congress_id):
    """ create an event within a congress """

    congress = get_object_or_404(Congress, pk=congress_id)

    # check access
    role = "events.org.%s.edit" % congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if request.method == "POST":

        form = EventForm(request.POST)

        if form.is_valid():
            event = Event()
            _update_event(request, form, event, congress, "Event added")
            return redirect(
                "events:edit_event", event_id=event.id, congress_id=congress_id
            )
        else:
            print(form.errors)

    else:
        # default youth discount to 50% if used
        initial = {}
        if congress.allow_youth_payment_discount:
            initial["entry_youth_payment_discount"] = 50

        form = EventForm(initial=initial)

    return render(
        request,
        "events/edit_event.html",
        {"form": form, "congress": congress, "page_type": "add"},
    )


@login_required
def edit_event(request, congress_id, event_id):
    """ edit an event within a congress """

    congress = get_object_or_404(Congress, pk=congress_id)

    # check access
    role = "events.org.%s.edit" % congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    event = get_object_or_404(Event, pk=event_id)
    sessions = Session.objects.filter(event=event).order_by(
        "session_date", "session_start"
    )

    if request.method == "POST":

        form = EventForm(request.POST, instance=event)

        if form.is_valid():
            _update_event(request, form, event, congress, "Event updated")
        else:
            print(form.errors)

    else:
        # datepicker is very fussy about format
        initial = {}
        if event.entry_open_date:
            initial["entry_open_date"] = event.entry_open_date.strftime("%d/%m/%Y")
        if event.entry_close_date:
            initial["entry_close_date"] = event.entry_close_date.strftime("%d/%m/%Y")
        form = EventForm(instance=event, initial=initial)

    categories = Category.objects.filter(event=event)

    return render(
        request,
        "events/edit_event.html",
        {
            "form": form,
            "congress": congress,
            "event": event,
            "sessions": sessions,
            "categories": categories,
            "page_type": "edit",
        },
    )


@login_required
def create_session(request, event_id):
    """ create session within an event  """

    event = get_object_or_404(Event, pk=event_id)

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if request.method == "POST":
        form = SessionForm(request.POST)
        if form.is_valid():
            session = Session()
            session.event = event
            session.session_date = form.cleaned_data["session_date"]
            session.session_start = form.cleaned_data["session_start"]
            session.session_end = form.cleaned_data["session_end"]
            session.save()

            messages.success(
                request, "Session Added", extra_tags="cobalt-message-success"
            )
            return redirect(
                "events:edit_event", event_id=event_id, congress_id=event.congress.id
            )
        else:
            print(form.errors)

    else:
        form = SessionForm()

    return render(
        request,
        "events/create_session.html",
        {"form": form, "event": event},
    )


@login_required
def edit_session(request, event_id, session_id):
    """ edit session within an event  """

    event = get_object_or_404(Event, pk=event_id)
    session = get_object_or_404(Session, pk=session_id)

    # check access
    role = "events.org.%s.edit" % event.congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if request.method == "POST":
        form = SessionForm(request.POST, instance=session)
        if form.is_valid():
            session.session_date = form.cleaned_data["session_date"]
            session.session_start = form.cleaned_data["session_start"]
            session.session_end = form.cleaned_data["session_end"]
            session.save()

            messages.success(
                request, "Session Updated", extra_tags="cobalt-message-success"
            )
            return redirect(
                "events:edit_event", event_id=event_id, congress_id=event.congress.id
            )
        else:
            print(form.errors)

    else:
        # datepicker is very fussy about format
        initial = {}
        if session.session_date:
            initial["session_date"] = session.session_date.strftime("%d/%m/%Y")
        if session.session_start:
            initial["session_start"] = session.session_start.strftime("%I:%M %p")
        if session.session_end:
            initial["session_end"] = session.session_end.strftime("%I:%M %p")

        form = SessionForm(instance=event, initial=initial)

    return render(
        request,
        "events/edit_session.html",
        {"form": form, "event": event, "session": session},
    )


@login_required
def view_draft_congresses(request):
    """ Show any draft congresses that the user can edit """

    draft_congresses = Congress.objects.filter(status="Draft")
    draft_congress_list = []
    for draft_congress in draft_congresses:
        role = "events.org.%s.edit" % draft_congress.congress_master.org.id
        if rbac_user_has_role(request.user, role):
            draft_congress_list.append(draft_congress)

    return render(
        request,
        "events/view_draft_congresses.html",
        {"congress_list": draft_congress_list},
    )


@login_required()
def manage_congress_download(request, congress_id):
    """ Manage download files """

    congress = get_object_or_404(Congress, pk=congress_id)

    # check access
    role = "events.org.%s.edit" % congress.congress_master.org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if request.method == "POST":
        form = CongressDownloadForm(request.POST, request.FILES)

        if form.is_valid():
            form.save()

            messages.success(
                request, "Document uploaded", extra_tags="cobalt-message-success"
            )

    form = CongressDownloadForm()

    # Get bulletins
    downloads = CongressDownload.objects.filter(congress=congress).order_by("-pk")

    return render(
        request,
        "events/congress_wizard_downloads.html",
        {"form": form, "congress": congress, "downloads": downloads},
    )
