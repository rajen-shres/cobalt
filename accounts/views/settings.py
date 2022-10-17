from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.http import HttpResponse
from django.shortcuts import render
from fcm_django.models import FCMDevice

from accounts.forms import UserSettingsForm
from accounts.models import APIToken, UnregisteredUser
from notifications.models import UnregisteredBlockedEmail
from notifications.views.user import notifications_in_english
from organisations.models import MemberClubEmail
from rbac.core import rbac_user_has_role


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

    # Check if user is a developer. When we have more than one role we may need a better approach such as a specific
    # RBAC role for developers.
    is_developer = rbac_user_has_role(request.user, "notifications.realtime_send.edit")

    # If user has a registered FCM device, show them the option to send a test message

    fcm_devices = FCMDevice.objects.filter(user=request.user).order_by("-date_created")

    # Get user sessions so they can manage them - maybe
    all_sessions = Session.objects.all()

    session_list = []

    for session in all_sessions:
        if (
            "_auth_user_id" in session.get_decoded()
            and int(session.get_decoded()["_auth_user_id"]) == request.user.id
        ):
            session_list.append(session)

    return render(
        request,
        "accounts/settings/user_settings.html",
        {
            "form": form,
            "notifications_list": notifications_list,
            "is_developer": is_developer,
            "fcm_devices": fcm_devices,
            # "sessions": session_list,
            # Comment out sessions for now
            "sessions": [],
        },
    )


@login_required()
def developer_settings_htmx(request):
    """Manage settings for developers. Built into the normal settings page"""

    if "add" in request.POST:
        APIToken(user=request.user).save()

    api_tokens = APIToken.objects.filter(user=request.user)

    return render(
        request, "accounts/developer/settings.html", {"api_tokens": api_tokens}
    )


@login_required()
def developer_settings_delete_token_htmx(request):
    """Delete a token for a developer"""

    APIToken.objects.filter(pk=request.POST.get("token_id"), user=request.user).delete()

    api_tokens = APIToken.objects.filter(user=request.user)

    return render(
        request, "accounts/developer/settings.html", {"api_tokens": api_tokens}
    )


def unregistered_user_settings(request, identifier):
    """allow an unregistered user to control their email preferences"""

    unregistered = UnregisteredUser.objects.filter(identifier=identifier).first()

    if not unregistered:
        return HttpResponse("Invalid identifier")

    # get any other emails related to this user
    additional_emails = MemberClubEmail.objects.filter(
        system_number=unregistered.system_number
    )

    # don't show if already blocked
    blocked_emails = UnregisteredBlockedEmail.objects.filter(
        un_registered_user=unregistered
    ).values_list("email", flat=True)

    for additional_email in additional_emails:
        if additional_email.email in blocked_emails:
            additional_email.email = None

    if request.POST:
        email = request.POST.get("block_email")

        if not email:
            return HttpResponse("An error occurred")

        block, _ = UnregisteredBlockedEmail.objects.get_or_create(
            un_registered_user=unregistered, email=email
        )
        block.save()

        return HttpResponse("Email removed. You will receive no further notifications.")

    return render(
        request,
        "accounts/settings/unregistered_user_settings.html",
        {
            "unregistered": unregistered,
            "additional_emails": additional_emails,
        },
    )
