import boto3
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.models import User, UnregisteredUser
from cobalt.settings import AWS_REGION_NAME, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
from notifications.views.core import remove_email_from_blocked_list
from organisations.models import MemberClubEmail
from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden


@login_required()
def admin_aws_suppression(request):
    """Manage AWS Email Suppression Lists. An email address gets put on a suppression list by AWS but we can remove
    it.

    This relies on the AWS CLI being installed which is done by .platform/hooks/rebuild/02_yum.sh

    In a development environment, you need to install this manually.

    To test any of this you need an environment with the notification playpen turned off so you can generate the
    entry on the suppression list in the first place. Note that if you use a different environment to do this then
    the reset will not occur there and you will not be able to generate further blocks.

    BE CAREFUL: We do not have separate AWS email environments. Test changes will impact production data.

    """

    # check access
    role = "notifications.admin.view"
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    message = ""

    # Create AWS API client
    client = boto3.client(
        "sesv2",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION_NAME,
    )

    if request.POST:
        email_address_to_remove = request.POST.get("email_address_to_remove")

        try:
            client.delete_suppressed_destination(EmailAddress=email_address_to_remove)
            message = f"Email block removed for {email_address_to_remove}"

            # Also remove from our internal list
            remove_email_from_blocked_list(email_address_to_remove)

        except Exception as exc:
            message = exc.__str__()

    # Get all entries on suppression list
    result = client.list_suppressed_destinations()
    data = result["SuppressedDestinationSummaries"]

    # Try to augment data
    email_list = [item["EmailAddress"] for item in data]

    # Users
    user_qs = User.objects.filter(email__in=email_list)
    email_to_user_dict = {user.email: user for user in user_qs}

    # UnregisteredUsers

    # Get the club email entries with email and system_number
    un_reg_emails = MemberClubEmail.objects.filter(email__in=email_list)

    # Create a dictionary of system_number to email address
    system_number_to_email_dict = {
        user.system_number: user.email for user in un_reg_emails
    }

    # Get a list of the system_numbers we want
    un_reg_emails_system_number_list = un_reg_emails.values("system_number")

    # Get the matching unregistered users
    un_reg_qs = UnregisteredUser.objects.filter(
        system_number__in=un_reg_emails_system_number_list
    )

    # add to the main dictionary
    for un_reg in un_reg_qs:
        un_reg.is_un_reg = True
        email_to_user_dict[system_number_to_email_dict[un_reg.system_number]] = un_reg

    suppression_list = [
        {
            "user": email_to_user_dict.get(item["EmailAddress"]),
            "email": item["EmailAddress"],
            "reason": item["Reason"],
            "last_update_time": item["LastUpdateTime"],
        }
        for item in data
    ]

    return render(
        request,
        "notifications/admin_aws_suppression.html",
        {"suppression_list": suppression_list, "message": message},
    )
