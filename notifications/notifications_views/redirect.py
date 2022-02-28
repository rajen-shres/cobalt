from django.shortcuts import redirect
from django.utils import timezone
from post_office.models import Email

from notifications.models import Snooper


def email_click_handler(request, message_id, redirect_path):
    """This is the entry point for email clicks so we know who has clicked on an email.
    Parameters are message_id (maps to Django Post Office id) and path. The path has ! instead of /
    """

    print("Inside email handler thingo", message_id)

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
