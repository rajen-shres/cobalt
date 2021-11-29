from post_office.models import Email

from tests.test_manager import CobaltTestManager


def check_email_sent(
    manager: CobaltTestManager,
    test_name: str,
    test_description: str,
    email_address: str = None,
    subject_search: str = None,
    body_search: str = None,
    email_count: int = 5,
):
    """Check if an email has been sent

    Args:
        manager: standard manager object
        test_name: Name for this test to appear in report
        test_description: Description for this test
        subject_search: string to search for in the email subject
        body_search: string to search for in the email body
        email_address: email address to search for
        email_count: how many recent emails to look through
    """

    last_email = Email.objects.order_by("-pk")[0].pk

    emails = Email.objects.filter(id__gt=last_email - email_count)

    if email_address:
        emails = emails.filter(to=email_address)

    if subject_search:
        emails = emails.filter(subject__icontains=subject_search)

    if body_search:
        emails = emails.filter(html_message__icontains=body_search)

    ok = emails.exists()

    output = f"Looked for email with to={email_address} subject has '{subject_search}' and body contains '{body_search}. Result was {ok}'"

    manager.save_results(
        status=ok,
        output=output,
        test_name=test_name,
        test_description=test_description,
    )
