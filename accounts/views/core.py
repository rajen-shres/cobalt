from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordResetForm, PasswordChangeForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import PasswordResetView
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes, force_text
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from accounts.forms import UserRegisterForm
from accounts.models import User, UnregisteredUser
from accounts.tokens import account_activation_token
from cobalt.settings import GLOBAL_TITLE, ALL_SYSTEM_ACCOUNTS
from logs.views import log_event
from masterpoints.views import user_summary
from notifications.views.core import send_cobalt_email_with_template
from organisations.models import MemberClubEmail, Organisation
from organisations.views.general import replace_unregistered_user_with_real_user


def register_user(request):
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

    form = UserRegisterForm(request.POST or None)

    if request.method == "POST":
        # See if this user registered before and didn't activate
        user = (
            User.objects.filter(system_number=request.POST.get("username"))
            .filter(is_active=False)
            .first()
        )
        if user:
            # reload form with this user as base
            form = UserRegisterForm(request.POST, instance=user)

        if form.is_valid():
            return _register_handle_valid_form(form, request)

    return render(request, "accounts/core/register.html", {"user_form": form})


def _register_handle_valid_form(form, request):
    user = form.save(commit=False)
    user.is_active = False  # not active until email confirmed
    user.system_number = user.username
    user.save()

    _check_duplicate_email(user)

    to_email = form.cleaned_data.get("email")
    html = (
        f"Thank you for signing up to the {GLOBAL_TITLE} site. "
        f"Please click on the link below to activate your account."
    )
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = account_activation_token.make_token(user)
    link = reverse("accounts:activate", kwargs={"uidb64": uid, "token": token})

    context = {
        "name": user.first_name,
        "title": f"Welcome to {GLOBAL_TITLE}",
        "email_body": html,
        "link": link,
        "link_text": "Activate Account",
        "subject": "Activate your Account",
    }

    send_cobalt_email_with_template(
        to_address=to_email, context=context, priority="now"
    )

    # Check if we have a matching UnregisteredUser object and copy data across
    _check_unregistered_user_match(user)

    return render(
        request, "accounts/core/register_complete.html", {"email_address": to_email}
    )


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
            "accounts/core/activate_complete.html",
            {"user": user, "others_same_email": others_same_email},
        )
    else:
        return HttpResponse("Activation link is invalid or already used!")


def password_reset_request(request):
    """handle password resets from users not logged in"""
    if request.method != "POST":
        form = PasswordResetForm()
        return render(
            request,
            "registration/password_reset_form.html",
            {"form": form},
        )

    form = PasswordResetForm(request.POST)

    if not form.is_valid():
        log_event(
            request=request,
            user="logged out",
            severity="WARN",
            source="Accounts",
            sub_source="password_reset",
            message=f"Attempt to reset password failed. Form invalid. Email: {request.POST.get('email')}",
        )

        return render(
            request,
            "registration/password_reset_form.html",
            {"form": form},
        )

    email = form.cleaned_data["email"]
    associated_users = User.objects.filter(email__iexact=email)

    email_body_base = (
        f"You are receiving this email because you requested a password reset for your account with "
        f"{GLOBAL_TITLE}. Click on the link below to reset your password.<br><br>"
    )

    if associated_users.count() > 1:
        email_body_base += (
            "<b>This email address is shared.</b> You should check the name above and "
            "only click on the link sent to the person who wants to reset their password.<br><br>"
        )

    if not associated_users:
        log_event(
            request=request,
            user="logged out",
            severity="WARN",
            source="Accounts",
            sub_source="password_reset",
            message=f"Attempt to reset password failed. No match for email address: {email}",
        )

    for user in associated_users:

        if user.is_active:
            link_type = "password_reset_confirm"
            link_text = "Reset Password"
            token = default_token_generator.make_token(user)
            email_body = email_body_base
            log_event(
                request=request,
                user="logged out",
                severity="INFO",
                source="Accounts",
                sub_source="password_reset",
                message=f"Password reset email sent to {user} at {email}",
            )

        else:
            link_type = "accounts:activate"
            link_text = "Activate Account"
            token = account_activation_token.make_token(user)
            email_body = (
                email_body_base
                + "<h3>This account has not been activated. You must activate "
                "the account first.</h3><br><br>"
            )
            log_event(
                request=request,
                user="logged out",
                severity="INFO",
                source="Accounts",
                sub_source="password_reset",
                message=f"Password reset (activation) email sent to {user} at {email}",
            )

        link = reverse(
            link_type,
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": token,
            },
        )

        context = {
            "name": user.first_name,
            "subject": "Password Reset",
            "title": "Password Reset Requested",
            "email_body": email_body,
            "link": link,
            "link_text": link_text,
        }

        send_cobalt_email_with_template(
            to_address=user.email, context=context, priority="now"
        )

    return redirect("password_reset_done")


def loggedout(request):
    """Should review if this is really needed."""
    return render(request, "accounts/core/loggedout.html")


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
                user=request.user,
                severity="INFO",
                source="Accounts",
                sub_source="change_password",
                message="Password change successful",
            )
            return redirect("accounts:user_profile")
        else:
            log_event(
                request=request,
                user=request.user,
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
    return render(request, "accounts/core/change_password.html", {"form": form})


def html_email_reset(request):
    """This is necessary so that we can provide an HTML email template
    for the password reset"""

    return PasswordResetView.as_view(
        html_email_template_name="registration/html_password_reset_email.html"
    )(request)


def _check_duplicate_email(user):
    """Check for a duplicate email address for this one"""

    others_same_email = (
        User.objects.filter(email=user.email).exclude(id=user.id).order_by("id")
    )

    for other_same_email in others_same_email:
        html = render_to_string("accounts/core/duplicate_email.html", {"user": user})

        context = {
            "name": other_same_email.first_name,
            "title": "Someone is Using Your Email Address",
            "email_body": html,
            "subject": "Email notification",
            "box_colour": "danger",
        }

        send_cobalt_email_with_template(
            to_address=other_same_email.email,
            context=context,
        )

    return others_same_email.exists()


def _check_unregistered_user_match(user):
    """See if there is already a user with this system_id in UnregisteredUser and cut across data"""

    unregistered_user = UnregisteredUser.objects.filter(
        system_number=user.system_number
    ).first()

    if not unregistered_user:
        return

    # Call the callbacks

    # Organisations
    replace_unregistered_user_with_real_user(user)

    # Now delete the unregistered user, we don't need it any more
    unregistered_user.delete()


def add_un_registered_user_with_mpc_data(
    system_number: int, club: Organisation, added_by: User, origin: str = "Manual"
) -> (str, dict):
    """Add an unregistered user to the system. Called from the player import if the user isn't already
    in the system"""

    # do nothing if user already exists
    if User.objects.filter(system_number=system_number).exists():
        return "user", None
    if UnregisteredUser.objects.filter(system_number=system_number).exists():
        return "un_reg", None

    # Get data from the MPC
    details = user_summary(system_number)

    if not details:
        return None, None

    # Create user
    UnregisteredUser(
        system_number=system_number,
        last_updated_by=added_by,
        last_name=details["Surname"],
        first_name=details["GivenNames"],
        # email=mpc_email,
        origin=origin,
        added_by_club=club,
    ).save()

    return "new", details


def get_user_or_unregistered_user_from_system_number(system_number):
    """return a User or UnregisteredUser object for a given system number"""

    # User takes precedence if somehow both exist (shouldn't happen)
    user = (
        User.objects.filter(system_number=system_number)
        .exclude(pk__in=ALL_SYSTEM_ACCOUNTS)
        .first()
    )

    if user:
        return user

    return UnregisteredUser.objects.filter(system_number=system_number).first()


def get_email_address_and_name_from_system_number(system_number, club=None):
    """returns email address for a user or unregistered user

    If we get a club passed in, then we check for club level overrides on the email address

    """

    # Try user
    user = (
        User.objects.filter(system_number=system_number)
        .exclude(id__in=ALL_SYSTEM_ACCOUNTS)
        .first()
    )

    if user:
        return user.email, user.first_name

    # try Unregistered user
    un_reg = UnregisteredUser.objects.filter(system_number=system_number).first()

    if not un_reg:
        return None, None

    # Check for club level overrides
    if club:
        override = MemberClubEmail.objects.filter(
            system_number=system_number, organisation=club
        )
    else:
        override = None

    if override:
        return override.email, un_reg.first_name

    return un_reg.email, un_reg.first_name


def get_users_or_unregistered_users_from_system_number_list(system_number_list):
    """takes a list of system numbers and returns a dictionary or User or UnregisteredUser objects
    indexed by system_number
    """

    # Get Users and UnregisteredUsers
    users = User.objects.filter(system_number__in=system_number_list)
    un_regs = UnregisteredUser.objects.filter(system_number__in=system_number_list)

    # Convert to a dictionary
    mixed_dict = {}

    for user in users:
        user.is_user = True
        mixed_dict[user.system_number] = {
            "type": "User",
            "value": user,
        }

    # Add unregistered to dictionary
    for un_reg in un_regs:
        un_reg.is_un_reg = True
        mixed_dict[un_reg.system_number] = {
            "type": "UnregisteredUser",
            "value": un_reg,
        }

    return mixed_dict
