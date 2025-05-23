from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404

from accounts.forms import UserUpdateForm, BlurbUpdateForm, PhotoUpdateForm
from accounts.models import UserAdditionalInfo, TeamMate, User
from accounts.views.core import _check_duplicate_email
from forums.models import Post, Comment1, Comment2
from masterpoints.views import user_summary

from organisations.club_admin_core import (
    block_club_for_user,
    clear_club_email_bounced,
    get_club_memberships_for_person,
    get_club_options_for_user,
    get_outstanding_membership_fees_for_user,
    get_member_details,
    has_club_email_bounced,
    share_user_data_with_clubs,
    unblock_club_for_user,
)
from organisations.models import MemberClubOptions
from payments.views.core import get_user_pending_payments
from rbac.core import rbac_user_has_role
from support.models import Incident
from utils.utils import cobalt_paginator


@login_required
def profile(request):
    """Profile update form.

    Allows a user to change their profile settings.

    Args:
        request - standard request object

    Returns:
        HttpResponse
    """

    form = UserUpdateForm(data=request.POST or None, instance=request.user)

    if request.method == "POST" and form.is_valid():

        form.save()
        feedback = "Profile Updated"

        if "email" in form.changed_data:
            if _check_duplicate_email(request.user):
                messages.warning(
                    request,
                    "This email is also being used by another member. This is allowed, but please check the "
                    "name on the email to see who it was intended for.",
                    extra_tags="cobalt-message-warning",
                )

            # Clear the bounce flag if set
            user_additional_info = UserAdditionalInfo.objects.filter(
                user=request.user
            ).first()
            if user_additional_info and user_additional_info.email_hard_bounce:
                user_additional_info.email_hard_bounce = False
                user_additional_info.email_hard_bounce_reason = None
                user_additional_info.save()

            if has_club_email_bounced(form.cleaned_data["email"]):
                clear_club_email_bounced(form.cleaned_data["email"])

        updated_clubs = share_user_data_with_clubs(request.user)
        if updated_clubs:
            feedback += f", {updated_clubs} club membership{'s' if updated_clubs>1 else ''} updated"

        messages.success(request, feedback, extra_tags="cobalt-message-success")

        # Reload form or dates don't work
        form = UserUpdateForm(instance=request.user)

    blurbform = BlurbUpdateForm(instance=request.user)
    photoform = PhotoUpdateForm(instance=request.user)

    team_mates = TeamMate.objects.filter(user=request.user).order_by(
        "team_mate__first_name"
    )

    user_additional_info = UserAdditionalInfo.objects.filter(user=request.user).first()

    # Get any outstanding debt
    user_pending_payments = get_user_pending_payments(request.user.system_number)

    # Show tour for this page?
    tour = request.GET.get("tour", None)

    return render(
        request,
        "accounts/profile/profile.html",
        {
            "form": form,
            "blurbform": blurbform,
            "photoform": photoform,
            "team_mates": team_mates,
            "user_additional_info": user_additional_info,
            "user_pending_payments": user_pending_payments,
            "tour": tour,
        },
    )


@login_required
def memberships_card_htmx(request, message=None, warning_message=False):
    """htmx end point for the membership card on the user profile page"""

    club_options = get_club_options_for_user(request.user)
    outstanding_fees = get_outstanding_membership_fees_for_user(request.user)

    return render(
        request,
        "accounts/profile/profile_memberships_card_htmx.html",
        {
            "club_options": club_options,
            "outstanding_fees": outstanding_fees,
            "share_data_choices": MemberClubOptions.SHARE_DATA_CHOICES,
            "membership_message": message,
            "warning_message": warning_message,
        },
    )


@login_required
def allow_membership_htmx(request):
    """toggle the allow membership setting on a club options row

    The POST is expected to incude:
        club_id: Organisation id of the club involved
        allow: 'YES' or 'NO'
    """

    message = None

    allow = request.POST.get("allow", "YES") == "YES"
    club_id = request.POST.get("club_id", None)

    if not club_id:
        return memberships_card_htmx(
            request, "Something went wrong", warning_message=True
        )

    if allow:
        # unblocking

        success, message, club = unblock_club_for_user(club_id, request.user)

        warning_message = not success
        if success:
            message = f"Unblocked - {club.name} can add you as a member"

    else:
        # blocking

        success, message, _ = block_club_for_user(club_id, request.user)

        warning_message = True
        if success:
            message = "The membership has been removed and the club blocked"

    return memberships_card_htmx(
        request,
        message=message,
        warning_message=warning_message,
    )


@login_required
def allow_auto_pay_htmx(request):
    """toggle the allow auto pay setting on a club options row"""

    club_options_id = request.POST.get("mco_id", None)
    club_options = MemberClubOptions.objects.get(pk=club_options_id)

    if club_options.user != request.user:
        return memberships_card_htmx(request)

    club_options.allow_auto_pay = not club_options.allow_auto_pay
    club_options.save()

    return memberships_card_htmx(request)


@login_required
def share_data_htmx(request):
    """change the data sharing setting on a club options row"""

    message = None

    club_options_id = request.POST.get("mco_id", None)
    club_options = MemberClubOptions.objects.get(pk=club_options_id)

    if club_options.user != request.user:
        return memberships_card_htmx(request)

    share_data_choice = request.POST.get(
        f"share-data-{club_options.club.id}", MemberClubOptions.SHARE_DATA_NEVER
    )

    if share_data_choice not in [
        choice for choice, _ in MemberClubOptions.SHARE_DATA_CHOICES
    ]:
        share_data_choice = MemberClubOptions.SHARE_DATA_NEVER

    club_options.share_data = share_data_choice
    club_options.save()

    if share_data_choice in [
        MemberClubOptions.SHARE_DATA_ONCE,
        MemberClubOptions.SHARE_DATA_ALWAYS,
    ]:

        member_details = get_member_details(
            club_options.club, request.user.system_number
        )

        updated = share_user_data_with_clubs(
            request.user,
            this_membership=member_details,
            initial=True,
        )

        if updated:
            message = f"{club_options.club.name} records updated"

    return memberships_card_htmx(request, message=message)


def blurb_form_upload(request):
    """Profile update sub-form. Handles the picture and about fields.

    Allows a user to change their profile settings.

    Args:
        request - standard request object

    Returns:
        HttpResponse
    """

    if request.method == "POST":
        blurbform = BlurbUpdateForm(request.POST, request.FILES, instance=request.user)
        if blurbform.is_valid():
            blurbform.save()
            messages.success(
                request, "Profile Updated", extra_tags="cobalt-message-success"
            )
        else:
            print(blurbform.errors)

    return redirect("accounts:user_profile")


def picture_form_upload(request):
    """Profile update sub-form. Handles the picture

    Allows a user to change their profile settings.

    Args:
        request - standard request object

    Returns:
        HttpResponse
    """

    if request.method == "POST":
        photoform = PhotoUpdateForm(request.POST, request.FILES, instance=request.user)
        if photoform.is_valid():
            photoform.save()
            messages.success(
                request, "Profile Updated", extra_tags="cobalt-message-success"
            )
        else:
            print(photoform.errors)

    return redirect("accounts:user_profile")


@login_required
def public_profile(request, pk):
    """Public Profile form.

    Shows public information about a member.

    Args:
        request - standard request object
        pk - key of User

    Returns:
        HttpResponse
    """

    pub_profile = get_object_or_404(User, pk=pk)

    post_list = Post.objects.filter(author=pub_profile).order_by("-created_date")
    comment1_list = Comment1.objects.filter(author=pub_profile).order_by(
        "-created_date"
    )
    comment2_list = Comment2.objects.filter(author=pub_profile).order_by(
        "-created_date"
    )

    # Get tab id from URL - this means we are on this tab
    tab = request.GET["tab"] if "tab" in request.GET else None
    posts_active = None
    comment1s_active = None
    comment2s_active = None

    # if we are on a tab then get the right page for that tab and page 1 for the others

    if not tab or tab == "posts":
        posts_active = "active"
        posts = cobalt_paginator(request, post_list)
        comment1s = cobalt_paginator(request, comment1_list, page_no=1)
        comment2s = cobalt_paginator(request, comment2_list, page_no=1)
    elif tab == "comment1s":
        comment1s_active = "active"
        posts = cobalt_paginator(request, post_list, page_no=1)
        comment1s = cobalt_paginator(request, comment1_list)
        comment2s = cobalt_paginator(request, comment2_list, page_no=1)
    elif tab == "comment2s":
        comment2s_active = "active"
        posts = cobalt_paginator(request, post_list, page_no=1)
        comment1s = cobalt_paginator(request, comment1_list, page_no=1)
        comment2s = cobalt_paginator(request, comment2_list)

    summary = user_summary(pub_profile.system_number)

    # Admins get more
    payments_admin = bool(rbac_user_has_role(request.user, "payments.global.edit"))
    events_admin = bool(rbac_user_has_role(request.user, "events.global.view"))

    if rbac_user_has_role(request.user, "support.helpdesk.edit"):
        tickets = Incident.objects.filter(reported_by_user=pub_profile.id)
    else:
        tickets = False

    email_admin = bool(rbac_user_has_role(request.user, "notifications.admin.view"))
    # real time is covered by the email role or one other
    real_time_admin = email_admin
    if real_time_admin:
        real_time_admin = bool(
            rbac_user_has_role(request.user, "notifications.realtime_send.edit")
        )

    user_additional_info = UserAdditionalInfo.objects.filter(user=pub_profile).first()

    # Get clubs
    member_of_clubs = get_club_memberships_for_person(pub_profile.system_number)

    return render(
        request,
        "accounts/profile/public_profile.html",
        {
            "profile": pub_profile,
            "posts": posts,
            "comment1s": comment1s,
            "comment2s": comment2s,
            "posts_active": posts_active,
            "comment1s_active": comment1s_active,
            "comment2s_active": comment2s_active,
            "summary": summary,
            "payments_admin": payments_admin,
            "events_admin": events_admin,
            "email_admin": email_admin,
            "real_time_admin": real_time_admin,
            "tickets": tickets,
            "user_additional_info": user_additional_info,
            "member_of_clubs": member_of_clubs,
        },
    )


@login_required()
def add_team_mate_ajax(request):
    """Ajax call to add a team mate

    Args:
        request(HTTPRequest): standard request

    Returns:
        HTTPResponse: success, failure or error
    """

    if request.method == "GET":
        member_id = request.GET.get("member_id")
        member = get_object_or_404(User, pk=member_id)
        team_mate = TeamMate.objects.filter(user=request.user, team_mate=member)
        if team_mate:  # already exists
            msg = f"{member.first_name} is already a team mate"
        else:
            team_mate = TeamMate(user=request.user, team_mate=member)
            team_mate.save()
            msg = "Success"

    else:
        msg = "Invalid request"

    response_data = {"message": msg}
    return JsonResponse({"data": response_data})


@login_required()
def delete_team_mate_ajax(request):
    """Ajax call to delete a team mate

    Args:
        request(HTTPRequest): standard request

    Returns:
        HTTPResponse: success, failure or error
    """
    if request.method == "GET":
        member_id = request.GET.get("member_id")
        member = get_object_or_404(User, pk=member_id)
        team_mate = TeamMate.objects.filter(team_mate=member, user=request.user)
        team_mate.delete()
        msg = "Success"

    else:
        msg = "Invalid request"

    response_data = {"message": msg}
    return JsonResponse({"data": response_data})


@login_required()
def toggle_team_mate_ajax(request):
    """Ajax call to switch the state of a team mate

    Args:
        request(HTTPRequest): standard request

    Returns:
        JsonResponse: message and first name
    """

    if request.method == "GET":
        member_id = request.GET["member_id"]
        member = User.objects.get(pk=member_id)
        team_mate = (
            TeamMate.objects.filter(user=request.user).filter(team_mate=member).first()
        )
        team_mate.make_payments = not team_mate.make_payments
        team_mate.save()
        msg = team_mate.make_payments

    else:
        msg = "Invalid request"

    response_data = {"message": msg, "first_name": team_mate.team_mate.first_name}
    return JsonResponse({"data": response_data})


@login_required()
def delete_photo(request):
    """Removes a user picture and resets to default

    Args:
        request(HTTPRequest): standard request

    Returns:
        Page
    """

    request.user.pic = "pic_folder/default-avatar.png"
    request.user.save()
    messages.success(
        request,
        "Your photo has been reset",
        extra_tags="cobalt-message-success",
    )

    return redirect("accounts:user_profile")
