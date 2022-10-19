import datetime
import json
import subprocess

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render

from accounts.models import User, UnregisteredUser
from cobalt.settings import AWS_REGION_NAME
from organisations.models import MemberClubEmail
from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden


@login_required()
def admin_aws_suppression(request):
    """Manage AWS Email Suppression Lists. An email address gets put on a suppression list by AWS but we can remove
    it.

    This relies on the AWS CLI being installed which is done by .platform/hooks/rebuild/02_yum.sh

    In a development environment, you need to install this manually.

    BE CAREFUL: We do not have separate AWS email environments. Test changes will impact production data.

    """

    # check access
    role = "notifications.admin.view"
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    message = ""

    if request.POST:
        email_address_to_remove = request.POST.get("email_address_to_remove")
        result = subprocess.run(
            [
                "/usr/local/bin/aws",
                "sesv2",
                "delete-suppressed-destination",
                "--email-address",
                email_address_to_remove,
                "--region",
                AWS_REGION_NAME,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout = f"{result.stdout}"
        stderr = f"{result.stderr}"
        if stderr == "":
            message = f"Email block removed. {stdout} {stderr}"
        else:
            message = f"Error removing block. {stdout} {stderr}"

    result = subprocess.run(
        [
            "/usr/local/bin/aws",
            "sesv2",
            "list-suppressed-destinations",
            "--region",
            AWS_REGION_NAME,
        ],
        stdout=subprocess.PIPE,
    )

    try:
        data = json.loads(result.stdout)["SuppressedDestinationSummaries"]
    except KeyError:
        return HttpResponse("No data found")

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
        email_to_user_dict[system_number_to_email_dict[un_reg.system_number]] = un_reg

    suppression_list = [
        {
            "user": email_to_user_dict.get(item["EmailAddress"]),
            "email": item["EmailAddress"],
            "reason": item["Reason"],
            "last_update_time": datetime.datetime.fromisoformat(item["LastUpdateTime"]),
        }
        for item in data
    ]

    return render(
        request,
        "notifications/admin_aws_suppression.html",
        {"suppression_list": suppression_list, "message": message},
    )
