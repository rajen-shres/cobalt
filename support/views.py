import json
from itertools import chain

import requests
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import SuspiciousOperation
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt

from accounts.models import User
from cobalt.settings import (
    COBALT_HOSTNAME,
    RECAPTCHA_SITE_KEY,
    RECAPTCHA_SECRET_KEY,
)
from events.models import Congress
from forums.models import Post, Forum
from organisations.models import Organisation
from payments.models import MemberTransaction
from rbac.core import rbac_user_has_role
from utils.utils import cobalt_paginator
from .forms import (
    HelpdeskLoggedInContactForm,
    HelpdeskLoggedOutContactForm,
)
from .helpdesk import notify_user_new_ticket_by_form, notify_group_new_ticket


@login_required
def home(request):

    helpdesk = bool(rbac_user_has_role(request.user, "support.helpdesk.view"))
    return render(request, "support/general/home.html", {"helpdesk": helpdesk})


@login_required
def admin(request):

    return render(request, "support/general/home_admin.html")


def cookies(request):
    return render(request, "support/general/cookies.html")


def guidelines(request):
    return render(request, "support/general/guidelines.html")


def acceptable_use(request):
    return render(request, "support/general/acceptable_use.html")


def non_production_email_changer(request):
    """Only for test systems - changes email address of all users"""

    if not request.user.is_superuser:
        raise SuspiciousOperation("This is only available for admin users.")

    if COBALT_HOSTNAME in ["myabf.com.au", "www.myabf.com.au"]:
        raise SuspiciousOperation(
            "Not for use in production. This cannot be used in a production system."
        )

    all_users = User.objects.all()

    if request.method == "POST":
        new_email = request.POST["new_email"]
        for user in all_users:
            user.email = new_email
            user.save()

        count = all_users.count()
        messages.success(
            request,
            f"{count} users updated.",
            extra_tags="cobalt-message-success",
        )

    return render(
        request,
        "support/development/non_production_email_changer.html",
        {"all_users": all_users},
    )


@login_required()
def contact_logged_in(request):
    """Contact form for logged in users"""

    form = HelpdeskLoggedInContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ticket = form.save()
        notify_user_new_ticket_by_form(request, ticket)
        notify_group_new_ticket(request, ticket)

        messages.success(
            request,
            "Helpdesk ticket logged. You will be informed of progress via email.",
            extra_tags="cobalt-message-success",
        )

        return redirect("support:support")

    return render(
        request,
        "support/contact/contact_logged_in.html",
        {
            "form": form,
        },
    )


def contact_logged_out(request):
    """Contact form for logged out users"""

    form = HelpdeskLoggedOutContactForm(request.POST or None)
    is_human = True  # Innocent until proven guilty

    if request.method == "POST" and form.is_valid():

        # Check with Google for status of recaptcha request
        recaptcha_token = request.POST.get("g-recaptcha-response")
        data = {"response": recaptcha_token, "secret": RECAPTCHA_SECRET_KEY}
        resp = requests.post(
            "https://www.google.com/recaptcha/api/siteverify", data=data
        )
        result_json = resp.json()

        is_human = bool(result_json.get("success"))

        if is_human:

            ticket = form.save()
            notify_user_new_ticket_by_form(request, ticket)
            notify_group_new_ticket(request, ticket)

            messages.add_message(
                request,
                messages.INFO,
                "Helpdesk ticket logged. You will be informed of progress via email.",
            )

            return redirect("/")

    return render(
        request,
        "support/contact/contact_logged_out.html",
        {
            "form": form,
            "site_key": RECAPTCHA_SITE_KEY,
            "is_human": is_human,
        },
    )


@login_required
@csrf_exempt
def browser_errors(request):
    """receive errors from browser code and notify support"""

    # Log to stdout only - emails disabled as too much noise from old browser

    if request.method == "POST":
        try:
            data = request.POST.get("data", None)
            if data:
                errors = json.loads(data)
                print(
                    f"Error from browser ignored: {errors['message']} User: {request.user}"
                )

        except Exception as err:
            print(err)

    return HttpResponse("ok")


@login_required
def search(request):
    """This handles the search bar that appears on every page. Also gets called from the search panel that
    we show if a search is performed, to allow the user to reduce the range of the search"""

    query = request.POST.get("search_string")
    include_people = request.POST.get("include_people")
    include_forums = request.POST.get("include_forums")
    include_posts = request.POST.get("include_posts")
    include_events = request.POST.get("include_events")
    include_payments = request.POST.get("include_payments")
    include_orgs = request.POST.get("include_orgs")

    searchparams = ""

    if query:  # don't search if no search string

        searchparams = f"search_string={query.replace(' ', '%20')}&"

        # Users
        if include_people:

            if query.find(" ") >= 0:
                first_name = query.split(" ")[0]
                last_name = " ".join(query.split(" ")[1:])
                people = User.objects.filter(
                    Q(first_name__icontains=first_name)
                    & Q(last_name__icontains=last_name)
                )
            else:
                people = User.objects.filter(
                    Q(first_name__icontains=query)
                    | Q(last_name__icontains=query)
                    | Q(system_number__icontains=query)
                )
            searchparams += "include_people=1&"
        else:
            people = []

        if include_posts:
            posts = Post.objects.filter(title__icontains=query)
            searchparams += "include_posts=1&"
        else:
            posts = []

        if include_forums:
            forums = Forum.objects.filter(title__icontains=query)
            searchparams += "include_forums=1&"
        else:
            forums = []

        if include_events:
            events = Congress.objects.filter(name__icontains=query)
            searchparams += "include_events=1&"
        else:
            events = []

        if include_payments:
            payments = MemberTransaction.objects.filter(description__icontains=query)
            searchparams += "include_payments=1&"
        else:
            payments = []

        if include_orgs:
            orgs = Organisation.objects.filter(name__icontains=query)
            searchparams += "include_orgs=1&"
        else:
            orgs = []

        # combine outputs
        results = list(chain(people, posts, forums, events, payments, orgs))

        # create paginator
        things = cobalt_paginator(request, results)

    else:  # no search string provided

        things = []

    return render(
        request,
        "support/general/search.html",
        {
            "things": things,
            "search_string": query,
            "include_people": include_people,
            "include_forums": include_forums,
            "include_posts": include_posts,
            "include_events": include_events,
            "include_payments": include_payments,
            "include_orgs": include_orgs,
            "searchparams": searchparams,
        },
    )
