# -*- coding: utf-8 -*-
"""Handles all activities associated with user accounts.

This module handles all of the functions relating to users such as creating
accounts, resetting passwords, searches. profiles etc.

"""
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.contrib.sites.shortcuts import get_current_site
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_text
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.auth import login
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.http import JsonResponse
from django.contrib.auth.views import PasswordResetView
import ipinfo
from notifications.views import send_cobalt_email, notifications_in_english
from logs.views import get_client_ip, log_event
from organisations.models import MemberOrganisation
from .models import User, TeamMate
from .tokens import account_activation_token
from .forms import (
    UserRegisterForm,
    UserUpdateForm,
    PhotoUpdateForm,
    BlurbUpdateForm,
    UserSettingsForm,
)
from forums.models import Post, Comment1, Comment2
from utils.utils import cobalt_paginator
from cobalt.settings import GLOBAL_ORG, RBAC_EVERYONE, TBA_PLAYER, COBALT_HOSTNAME
from masterpoints.views import user_summary


def html_email_reset(request):
    """This is necessary so that we can provide an HTML email template
    for the password reset"""

    return PasswordResetView.as_view(
        html_email_template_name="registration/html_password_reset_email.html"
    )(request)


def register(request):
    """User registration form

    This form allows a user to register for the system. The form includes
    Ajax code to look up the system number and pre-fill the first and last name.

    This form also sends the email to the user to confirm the email address
    is valid.

    Args:
        request - standard request object

    Returns:
        HttpResponse
    """

    if request.method == "POST":
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False  # not active until email confirmed
            user.system_number = user.username
            user.save()

            # Check for duplicate emails
            others_same_email = (
                User.objects.filter(email=user.email).exclude(id=user.id).order_by("id")
            )
            for other_same_email in others_same_email:
                msg = f"""A new user - {user} - has registered using the same email address as you.
                This is supported to allow couples to share the same email address. Only the first
                registered user can login using the email address. All users can login with their
                {GLOBAL_ORG} number.<br><br>
                All messages for any of the users will be sent to the same email address but will
                usually have the first name present to allow you to determine who the message was
                intended for.<br><br>
                We recommend that every user has a unique email address, but understand that some
                people wish to share an email.<br><br><br>
                The {GLOBAL_ORG} Technology Team
                """
                context = {
                    "name": other_same_email.first_name,
                    "title": "Someone Using Your Email Address",
                    "email_body": msg,
                    "host": COBALT_HOSTNAME,
                }

                html_msg = render_to_string("notifications/email.html", context)

                # send
                send_cobalt_email(
                    other_same_email.email,
                    f"{user} is using your email address",
                    html_msg,
                )

            current_site = get_current_site(request)
            mail_subject = "Activate your account."
            message = render_to_string(
                "accounts/acc_active_email.html",
                {
                    "user": user,
                    "domain": current_site.domain,
                    "org": settings.GLOBAL_ORG,
                    "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                    "token": account_activation_token.make_token(user),
                },
            )
            to_email = form.cleaned_data.get("email")
            send_cobalt_email(to_email, mail_subject, message)
            return render(
                request, "accounts/register_complete.html", {"email_address": to_email}
            )
    else:
        form = UserRegisterForm()

    return render(request, "accounts/register.html", {"user_form": form})


def activate(request, uidb64, token):
    """User activation form

    This is the link sent to the user over email. If the link is valid, then
    the user is logged in, otherwise they are notified that the link is not
    valid.

    Args:
        request - standard request object
        uidb64 - encrypted user id
        token - generated token

    Returns:
        HttpResponse
    """
    try:
        uid = force_text(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    if user is not None and account_activation_token.check_token(user, token):
        user.is_active = True
        user.save()
        login(request, user)
        # Check for multiple email addresses
        others_same_email = (
            User.objects.filter(email=user.email).exclude(id=user.id).order_by("id")
        )
        return render(
            request,
            "accounts/activate_complete.html",
            {"user": user, "others_same_email": others_same_email},
        )
    else:
        return HttpResponse("Activation link is invalid or already used!")


def loggedout(request):
    """ Should review if this is really needed. """
    return render(request, "accounts/loggedout.html")


@login_required()
def change_password(request):
    """Password change form

    Allows a user to change their password.

    Args:
        request - standard request object

    Returns:
        HttpResponse
    """
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Important!
            messages.success(
                request,
                "Your password was successfully updated!",
                extra_tags="cobalt-message-success",
            )
            log_event(
                request=request,
                user=request.user.full_name,
                severity="INFO",
                source="Accounts",
                sub_source="change_password",
                message="Password change successful",
            )
            return redirect("accounts:user_profile")
        else:
            log_event(
                request=request,
                user=request.user.full_name,
                severity="WARN",
                source="Accounts",
                sub_source="change_password",
                message="Password change failed",
            )
            messages.error(
                request,
                "Please correct the error below.",
                extra_tags="cobalt-message-error",
            )
    else:
        form = PasswordChangeForm(request.user)
    return render(request, "accounts/change_password.html", {"form": form})


@login_required()
def member_detail_m2m_ajax(request):
    """Returns basic public info on a member. ONLY USED BY MEMBER TRANSFER. REPLACE.

    Ajax call to get basic info on a member. Will return an empty json array
    if the member number is invalid.

    Args:
        member_id - member number

    Returns:
        Json array: member, clubs,  global org name.
    """

    if request.method == "GET":
        if "member_id" in request.GET:
            member_id = request.GET.get("member_id")
            member = get_object_or_404(User, pk=member_id)
            clubs = MemberOrganisation.objects.filter(member=member)
            if request.is_ajax:
                global_org = settings.GLOBAL_ORG
                html = render_to_string(
                    template_name="accounts/member_ajax.html",
                    context={
                        "member": member,
                        "clubs": clubs,
                        "global_org": global_org,
                    },
                )
                data_dict = {"data": html}
                return JsonResponse(data=data_dict, safe=False)
    return JsonResponse(data={"error": "Invalid request"})


@login_required()
def member_details_ajax(request):
    """Returns basic public info on a member for the generic member search.

    Ajax call to get basic info on a member. Will return an empty json array
    if the member number is invalid.

    Args:
        member_id - member number
        search_id - used if page has multiple user searches. We just pass this
        through. Optional.

    Returns:
        Json array: member, clubs,  global org name.
    """

    if request.method == "GET":

        if "search_id" in request.GET:
            search_id = request.GET.get("search_id")
        else:
            search_id = None

        if "member_id" in request.GET:
            member_id = request.GET.get("member_id")
            member = get_object_or_404(User, pk=member_id)
            clubs = MemberOrganisation.objects.filter(member=member)
            if request.is_ajax:
                global_org = settings.GLOBAL_ORG
                html = render_to_string(
                    template_name="accounts/member_details_ajax.html",
                    context={
                        "member": member,
                        "clubs": clubs,
                        "global_org": global_org,
                        "search_id": search_id,
                    },
                )
                data_dict = {
                    "data": html,
                    "member": "%s" % member,
                    "pic": f"{member.pic}",
                }
                return JsonResponse(data=data_dict, safe=False)
    return JsonResponse(data={"error": "Invalid request"})


@login_required()
def search_ajax(request):
    """Ajax member search function. ONLY USED BY MEMBER TRANSFER. REPLACE.

    Used to search for members by the Member to Member transfer part of Payments.
    Currently very specific to payments. Could be made more generic if other
    parts of the system need a search function.

    Args:
        lastname - partial lastname to search for. Wild cards the ending.
        firstname - partial firstname to search for. Wild cards the ending.

    Returns:
        HttpResponse - either a message or a list of users in HTML format.
    """

    msg = ""

    if request.method == "GET":

        if "lastname" in request.GET:
            search_last_name = request.GET.get("lastname")
        else:
            search_last_name = None

        if "firstname" in request.GET:
            search_first_name = request.GET.get("firstname")
        else:
            search_first_name = None

        if search_first_name and search_last_name:
            members = User.objects.filter(
                first_name__istartswith=search_first_name,
                last_name__istartswith=search_last_name,
            ).exclude(pk=request.user.id)
        elif search_last_name:
            members = User.objects.filter(
                last_name__istartswith=search_last_name
            ).exclude(pk=request.user.id)
        else:
            members = User.objects.filter(
                first_name__istartswith=search_first_name
            ).exclude(pk=request.user.id)

        if request.is_ajax:
            if members.count() > 30:
                msg = "Too many results (%s)" % members.count()
                members = None
            elif members.count() == 0:
                msg = "No matches found"
            html = render_to_string(
                template_name="accounts/search_results.html",
                context={"members": members, "msg": msg},
            )

            data_dict = {"data": html}

            return JsonResponse(data=data_dict, safe=False)

    return render(
        request,
        "accounts/search_results.html",
        context={"members": members, "msg": msg},
    )


@login_required()
def member_search_ajax(request):
    """Ajax member search function. Used by the generic member search.

    Used to search for members by the Member to Member transfer part of Payments.
    Currently very specific to payments. Could be made more generic if other
    parts of the system need a search function.

    Args:
        lastname - partial lastname to search for. Wild cards the ending.
        firstname - partial firstname to search for. Wild cards the ending.
        search_id - used if page has multiple user searches. We just pass this
        through. Optional.

    Returns:
        HttpResponse - either a message or a list of users in HTML format.
    """

    msg = ""

    if request.method == "GET":

        if "search_id" in request.GET:
            search_id = request.GET.get("search_id")
        else:
            search_id = None

        if "lastname" in request.GET:
            search_last_name = request.GET.get("lastname")
        else:
            search_last_name = None

        if "firstname" in request.GET:
            search_first_name = request.GET.get("firstname")
        else:
            search_first_name = None

        exclude_list = [request.user.id, RBAC_EVERYONE, TBA_PLAYER]

        if search_first_name and search_last_name:
            members = User.objects.filter(
                first_name__istartswith=search_first_name,
                last_name__istartswith=search_last_name,
            ).exclude(pk__in=exclude_list)
        elif search_last_name:
            members = User.objects.filter(
                last_name__istartswith=search_last_name
            ).exclude(pk__in=exclude_list)
        else:
            members = User.objects.filter(
                first_name__istartswith=search_first_name
            ).exclude(pk__in=exclude_list)

        if request.is_ajax:
            if members.count() > 30:
                msg = "Too many results (%s)" % members.count()
                members = None
            elif members.count() == 0:
                msg = "No matches found"
            html = render_to_string(
                template_name="accounts/search_results_ajax.html",
                context={"members": members, "msg": msg, "search_id": search_id},
            )

            data_dict = {"data": html}

            return JsonResponse(data=data_dict, safe=False)

    return render(
        request,
        "accounts/search_results_ajax.html",
        context={"members": members, "msg": msg},
    )


@login_required()
def system_number_search_ajax(request):
    """Ajax system_number search function. Used by the generic member search.

    Args:
        system_number - exact number to search for

    Returns:
        HttpResponse - either a message or a list of users in HTML format.
    """

    if request.method == "GET":
        exclude_list = [request.user.system_number, RBAC_EVERYONE, TBA_PLAYER]

        if "system_number" in request.GET:
            system_number = request.GET.get("system_number")
            member = User.objects.filter(system_number=system_number).first()
        else:
            system_number = None
            member = None

        if member and member.system_number not in exclude_list:
            status = "Success"
            msg = "Found member"
            member_id = member.id
        else:
            status = "Not Found"
            msg = f"No matches found for that {GLOBAL_ORG} number"
            member_id = 0

        data = {"member_id": member_id, "status": status, "msg": msg}

        data_dict = {"data": data}
        return JsonResponse(data=data_dict, safe=False)

    return JsonResponse(data={"error": "Invalid request"})


@login_required
def profile(request):
    """Profile update form.

    Allows a user to change their profile settings.

    Args:
        request - standard request object

    Returns:
        HttpResponse
    """

    if request.method == "POST":
        form = UserUpdateForm(data=request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            # auto top up select list needs to be refreshed
            # Fix DOB format for browser - expects DD/MM/YYYY
            if request.user.dob:
                request.user.dob = request.user.dob.strftime("%d/%m/%Y")
            form = UserUpdateForm(instance=request.user)
            messages.success(
                request, "Profile Updated", extra_tags="cobalt-message-success"
            )
    else:
        # Fix DOB format for browser - expects DD/MM/YYYY
        if request.user.dob:
            request.user.dob = request.user.dob.strftime("%d/%m/%Y")

        form = UserUpdateForm(instance=request.user)
    blurbform = BlurbUpdateForm(instance=request.user)
    photoform = PhotoUpdateForm(instance=request.user)

    team_mates = TeamMate.objects.filter(user=request.user).order_by(
        "team_mate__first_name"
    )

    context = {
        "form": form,
        "blurbform": blurbform,
        "photoform": photoform,
        "team_mates": team_mates,
    }
    return render(request, "accounts/profile.html", context)


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

    PAGE_SIZE = 30

    pub_profile = get_object_or_404(User, pk=pk)

    post_list = Post.objects.filter(author=pub_profile).order_by("-created_date")
    comment1_list = Comment1.objects.filter(author=pub_profile).order_by(
        "-created_date"
    )
    comment2_list = Comment2.objects.filter(author=pub_profile).order_by(
        "-created_date"
    )

    # Get tab id from URL - this means we are on this tab
    if "tab" in request.GET:
        tab = request.GET["tab"]
    else:
        tab = None

    posts_active = None
    comment1s_active = None
    comment2s_active = None

    # if we are on a tab then get the right page for that tab and page 1 for the others

    if not tab or tab == "posts":
        posts_active = "active"
        posts = cobalt_paginator(request, post_list, PAGE_SIZE)
        comment1s = cobalt_paginator(request, comment1_list, PAGE_SIZE, 1)
        comment2s = cobalt_paginator(request, comment2_list, PAGE_SIZE, 1)
    elif tab == "comment1s":
        comment1s_active = "active"
        posts = cobalt_paginator(request, post_list, PAGE_SIZE, 1)
        comment1s = cobalt_paginator(request, comment1_list, PAGE_SIZE)
        comment2s = cobalt_paginator(request, comment2_list, PAGE_SIZE, 1)
    elif tab == "comment2s":
        comment2s_active = "active"
        posts = cobalt_paginator(request, post_list, PAGE_SIZE, 1)
        comment1s = cobalt_paginator(request, comment1_list, PAGE_SIZE, 1)
        comment2s = cobalt_paginator(request, comment2_list, PAGE_SIZE)

    summary = user_summary(pub_profile.system_number)

    print(summary)

    return render(
        request,
        "accounts/public_profile.html",
        {
            "profile": pub_profile,
            "posts": posts,
            "comment1s": comment1s,
            "comment2s": comment2s,
            "posts_active": posts_active,
            "comment1s_active": comment1s_active,
            "comment2s_active": comment2s_active,
            "summary": summary,
        },
    )


@login_required
def user_settings(request):
    """User settings form.

    Allow user to choose preferences

    Args:
        request - standard request object

    Returns:
        HttpResponse
    """

    if request.method == "POST":
        form = UserSettingsForm(data=request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(
                request, "Settings saved.", extra_tags="cobalt-message-success"
            )
    else:
        form = UserSettingsForm(instance=request.user)

    notifications_list = notifications_in_english(request.user)

    return render(
        request,
        "accounts/user_settings.html",
        {"form": form, "notifications_list": notifications_list},
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
        member_id = request.GET["member_id"]
        member = User.objects.get(pk=member_id)
        team_mate = TeamMate.objects.filter(user=request.user, team_mate=member)
        if team_mate:  # already exists
            msg = f"{member.first_name} is already a team mate"
        else:
            team_mate = TeamMate(user=request.user, team_mate=member)
            team_mate.save()
            msg = "Success"

    else:
        msg = "Invalid request"

    response_data = {}
    response_data["message"] = msg
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
        member_id = request.GET["member_id"]
        member = User.objects.get(pk=member_id)
        team_mate = TeamMate.objects.filter(team_mate=member, user=request.user)
        team_mate.delete()
        msg = "Success"

    else:
        msg = "Invalid request"

    response_data = {}
    response_data["message"] = msg
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

    response_data = {}
    response_data["message"] = msg
    response_data["first_name"] = team_mate.team_mate.first_name
    return JsonResponse({"data": response_data})


@login_required()
def user_signed_up_list(request):
    """Show users who have signed up

    Args:
        request(HTTPRequest): standard request

    Returns:
        Page
    """

    users = User.objects.order_by("-date_joined")

    things = cobalt_paginator(request, users)

    total_users = User.objects.count()

    return render(
        request,
        "accounts/user_signed_up_list.html",
        {"things": things, "total_users": total_users},
    )


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
        request, "Your photo has been reset", extra_tags="cobalt-message-success",
    )

    return redirect("accounts:user_profile")
