from django.shortcuts import redirect
from django.utils import timezone
from post_office.models import Email

from notifications.models import Snooper


def email_create_click_link(message_id, path):
    """Create a link to apply to an email so that when a user clicks on it we can record the
    activity and redirect them to where they want to go

    Args:
        path(str): relative path they are trying to get to
        message_id(str): Django Post Office message id
    """

    path = path.replace("/", "!")

    return f"{message_id}/{path}"


def email_click_handler(request, message_id, redirect_path):
    """This is the entry point for email clicks so we know who has clicked on a link in an email.
    Parameters are message_id (maps to Django Post Office id) and path. The path has ! instead of /
    """

    # TODO: This is not in use yet. We need to change the email sender to use these links and it also
    # TODO: needs to be extended to allow urls for other sites
    # TODO: To implement you need to go to AWS SES and change the configuration set to not track clicks

    # Try to load Django Post Office email with this id
    email = Email.objects.filter(message_id=message_id).first()
    if email:

        # Try to find matching Snooper object
        snooper = Snooper.objects.filter(post_office_email=email).first()

        # Update click count
        if snooper:
            snooper.ses_clicked_count += 1
            snooper.ses_last_clicked_at = timezone.now()
            snooper.save()

    return redirect("/" + redirect_path.replace("!", "/"))
