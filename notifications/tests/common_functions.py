from post_office.models import Email

from tests.test_manager import CobaltTestManagerIntegration


def check_email_sent(
    manager: CobaltTestManagerIntegration,
    test_name: str,
    test_description: str,
    email_to: str = None,
    subject_search: str = None,
    body_search: str = None,
    email_count: int = 10,
):
    """Check if an email has been sent. This isn't the greatest test going around. Email addresses get changed
        by the playpen checks and you can also find older emails that match by accident. Emails really need to
        be manually tested as you need to look at the presentation as well as the content, but this is better
        than nothing.

    Args:
        manager: standard manager object
        test_name: Name for this test to appear in report
        test_description: Description for this test
        subject_search: string to search for in the email subject
        body_search: string to search for in the email body
        email_to: first name of person sent the email. Assumes using normal templates for this.
        email_count: how many recent emails to look through
    """

    last_email = Email.objects.order_by("-pk")[0].pk

    # We can't use the ORM to filter emails, we need to call Django Post Office functions
    emails = Email.objects.filter(id__gt=last_email - email_count)

    ok, output = _check_email_sent_tests(
        email_count, email_to, emails, subject_search, body_search
    )

    output += f"Result was {ok}"

    manager.save_results(
        status=ok,
        output=output,
        test_name=test_name,
        test_description=test_description,
    )


def _check_email_sent_tests(email_count, email_to, emails, subject_search, body_search):
    """Sub step of check_email_sent. Does the actual checking."""

    ok = False
    output = f"Looked through last {email_count} emails for an email with "

    if email_to:
        output += f"to={email_to} "
        for email in emails:
            if email.context["name"] == email_to:
                ok = True
            else:
                emails.exclude(pk=email.id)
        if not ok:
            output += "Failed on email_to. "
            return ok, output

    if subject_search:
        ok = False
        output += f"subject has '{subject_search}' "
        for email in emails:
            if email.context["subject"].find(subject_search) >= 0:
                ok = True
            else:
                emails.exclude(pk=email.id)
        if not ok:
            output += "Failed on subject_search. "
            return ok, output

    if body_search:
        ok = False
        output += f"body contains '{body_search}' "
        for email in emails:
            print("###########################")
            print(email.context["email_body"].find(body_search))
            print(body_search)
            print(email.context["email_body"])
            if email.context["email_body"].find(body_search) >= 0:
                ok = True
        if not ok:
            output += "Failed on body_search. "
            return ok, output

    return ok, output
