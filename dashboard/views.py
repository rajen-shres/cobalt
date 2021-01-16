""" views for dashboard """

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from masterpoints.views import get_masterpoints
from payments.core import get_balance_detail
from events.core import get_events

# from forums.views import post_list_dashboard
from utils.utils import cobalt_paginator
from forums.models import Post, ForumFollow
from rbac.core import rbac_user_blocked_for_model
from django.shortcuts import redirect
import logging

logger = logging.getLogger("django")


@login_required()
def dashboard(request):
    """ view to force the login prompt to come up """
    return home(request)


def home(request):
    """ Home page """

    if request.user.is_authenticated:
        system_number = request.user.system_number
        masterpoints = get_masterpoints(system_number)
        payments = get_balance_detail(request.user)
        posts = get_posts(request)
        posts2 = get_announcements(request)
        events, unpaid = get_events(request.user)

        return render(
            request,
            "dashboard/home.html",
            {
                "mp": masterpoints,
                "payments": payments,
                "posts": posts,
                "posts2": posts2,
                "events": events,
                "unpaid": unpaid,
            },
        )

    else:  # not logged in
        return redirect("logged_out")


def logged_out(request):
    """ Home screen for logged out users """

    posts = get_announcements_logged_out()
    return render(request, "dashboard/logged_out.html", {"posts": posts})


@login_required()
def scroll1(request):
    """Cutdown homepage to be called by infinite scroll.

    This handles the right column - discussion posts

    Infinite scroll will call this when the user scrolls off the bottom
    of the page. We don't need to update anything except the posts so exclude
    other front page database hits."""

    posts = get_posts(request)
    return render(request, "dashboard/home.html", {"posts": posts})


@login_required()
def scroll2(request):
    """Cutdown homepage to be called by infinite scroll.

    This handles the left column - announcements

    Infinite scroll will call this when the user scrolls off the bottom
    of the page. We don't need to update anything except the posts so exclude
    other front page database hits."""

    posts2 = get_announcements(request)
    return render(request, "dashboard/home.html", {"posts2": posts2})


def get_announcements(request):
    """ internal function to get Posts for forum_type="Announcements" """

    # TODO: Add clubs
    posts_list = Post.objects.filter(forum__forum_type="Announcement").order_by(
        "-created_date"
    )

    return cobalt_paginator(request, posts_list, 20)


def get_posts(request):
    """ internal function to get Posts """

    # Get users preferences plus default Forums
    # TODO: ADD EVERYONE
    forum_list = list(
        ForumFollow.objects.filter(user=request.user).values_list("forum", flat=True)
    )

    # get list of forums user cannot access
    blocked = rbac_user_blocked_for_model(
        user=request.user, app="forums", model="forum", action="view"
    )

    # Remove anything blocked
    if forum_list:
        forum_list_allowed = [item for item in forum_list if item not in blocked]
        posts_list = (
            Post.objects.filter(forum__in=forum_list_allowed)
            .filter(forum__forum_type="Discussion")
            .order_by("-created_date")
        )

    # Otherwise load everything not blocked
    else:
        posts_list = (
            Post.objects.exclude(forum__in=blocked)
            .filter(forum__forum_type="Discussion")
            .order_by("-created_date")
        )

    posts = cobalt_paginator(request, posts_list, 20)

    return posts


def get_announcements_logged_out():
    """ internal function to get Posts for logged out users
        For now just return the latest 3 posts in Forum id=1
    """

    posts = Post.objects.all().order_by("-created_date")[:3]
    return posts
