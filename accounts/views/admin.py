from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User, UnregisteredUser
from cobalt.settings import GLOBAL_TITLE, GLOBAL_ORG
from logs.views import log_event

# from masterpoints.views import user_summary
from notifications.views.core import send_cobalt_email_with_template
from organisations.models import Organisation
from organisations.club_admin_core import mark_player_as_deceased
from utils.utils import cobalt_paginator


@login_required()
@require_POST
def admin_toggle_user_is_active(request):
    """Activate or deactivate a user"""

    if not request.user.is_superuser:
        return HttpResponse("Forbidden")

    if "user_id" in request.POST:

        user_id = request.POST.get("user_id")
        user = get_object_or_404(User, pk=user_id)
        user.is_active = not user.is_active
        user.save()

        log_event(
            request.user,
            "WARN",
            "Accounts",
            "admin-activate",
            f"{user} is_active status changed to {user.is_active}",
        )

    return render(
        request, "accounts/profile/public_profile_header_admin.html", {"profile": user}
    )


@login_required()
@require_POST
def admin_mark_user_deceased(request):
    """Mark user as deceased"""

    if not request.user.is_superuser:
        return HttpResponse("Forbidden")

    if "user_id" in request.POST:

        user_id = request.POST.get("user_id")
        user = get_object_or_404(User, pk=user_id)

        mark_player_as_deceased(user.system_number, request.user)

        log_event(
            request.user,
            "WARN",
            "Accounts",
            "admin-deceased",
            f"{user} marked as deceased",
        )

        user = get_object_or_404(User, pk=user_id)

    return render(
        request, "accounts/profile/public_profile_header_admin.html", {"profile": user}
    )


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
        "accounts/general/user_signed_up_list.html",
        {"things": things, "total_users": total_users},
    )


def invite_to_join(
    un_reg: UnregisteredUser,
    email: str,
    requested_by_user: User,
    requested_by_org: Organisation,
):
    """Invite an unregistered user to sign up

    Args:
        un_reg: An unregistered user object
        email: email address to send to
        requested_by_user: User who is inviting this person
        requested_by_org: Org making request

    """

    email_body = f"""
                    {requested_by_user.full_name} from {requested_by_org} is inviting you to sign up for
                    {GLOBAL_TITLE}. This is free for {GLOBAL_ORG} members.
                    <br><br>
                    Benefits of signing up include:
                    <ul>
                    <li>View and enter events across the country
                    <li>Use a single account to pay for all you bridge at participating clubs
                    <li>Use credit card auto top up to add funds to your account automatically
                    <li>Use club pre-paid systems to pay for your normal duplicate bridge
                    <li>Manage your preference to receive information on things that interest you
                    <li>Use forums to follow topics of interest and to communicate with other members
                    </ul>
                    Click the link below to sign up now. It's Free!
                    <br><br>
    """
    link = reverse(
        "accounts:register",
        kwargs={"system_number": un_reg.system_number, "email": email},
    )

    context = {
        "name": un_reg.first_name,
        "title": f"Sign Up for {GLOBAL_TITLE}",
        "link_text": "Sign Up",
        "link": link,
        "email_body": email_body,
        "unregistered_identifier": un_reg.identifier,
    }

    if send_cobalt_email_with_template(
        to_address=email,
        context=context,
        apply_default_template_for_club=requested_by_org,
    ):
        un_reg.last_registration_invite_sent = timezone.now()
        un_reg.last_registration_invite_by_user = requested_by_user
        un_reg.last_registration_invite_by_club = requested_by_org
        un_reg.save()
        return True

    return False
