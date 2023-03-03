"""

Daily task to inform conveners about congresses which have finished and there are unpaid entries,
also fixes congresses if they qualify.

"""
import datetime

from dateutil.relativedelta import relativedelta
from django.core.management.base import BaseCommand
from django.urls import reverse

from accounts.models import User
from cobalt.settings import ABF_USER
from events.views.core import (
    get_completed_congresses_with_money_due,
    fix_closed_congress,
)

# Set thresholds
from notifications.views.core import send_cobalt_email_with_template

FIRST_WARNING_DAYS = 2
AUTO_FIX_UNLESS_OVERRIDDEN_DAYS = 1
AUTO_FIX_REGARDLESS_MONTHS = 3


def send_first_warning(congress):
    """send the first warning to the convener"""

    print("Sending first warning for", congress)

    email_body = f"""
                    <h1>Completed Congress with Outstanding Payments</h1>
                    <p>You are registered as the contact email for <b>{congress}</b> on MyABF that finished
                    {FIRST_WARNING_DAYS} days ago.</p>
                    <p>This congress still has outstanding payments due.<p>
                    <p>You have three options:<p>
                    <ol>
                    <li>Do nothing and we will automatically close off the payments in
                    {AUTO_FIX_UNLESS_OVERRIDDEN_DAYS - FIRST_WARNING_DAYS} days.
                    <li>Click on the link below to edit the congress and correct payments now.
                    <li>Click on the link below to prevent automatic closure of this congress to give you
                    more time to sort out the missing payments.
                    <ul>
    """

    context = {
        "name": "Tournament Organiser",
        "title": f"Congress Requiring Attention - {congress}",
        "email_body": email_body,
        "box_colour": "primary",
        "link": reverse("events:admin_summary", kwargs={"congress_id": congress.id}),
        "link_text": "View Congress",
    }

    send_cobalt_email_with_template(to_address=congress.contact_email, context=context)


def send_last_warning(congress):
    """send the last warning to the convener"""

    if congress.do_not_auto_close_congress:
        print(f"{congress} is set to not auto close")
        return

    print(f"Sending last warning for {congress}")

    email_body = f"""
                     <h1>Completed Congress with Outstanding Payments - Final Notice</h1>
                     <p>You are registered as the contact email for <b>{congress}</b> on MyABF that finished
                     {FIRST_WARNING_DAYS} days ago.</p>
                     <p>This congress still has outstanding payments due.<p>
                     <p>You have three options:<p>
                     <ol>
                     <li>Do nothing and we will automatically close off the payments in
                     {AUTO_FIX_UNLESS_OVERRIDDEN_DAYS} days.
                     <li>Click on the link below to edit the congress and correct payments now.
                     <li>Click on the link below to prevent automatic closure of this congress to give you
                     more time to sort out the missing payments.
                     <ul>
     """

    context = {
        "name": "Tournament Organiser",
        "title": f"Congress Requiring Attention - Final Notice - {congress}",
        "email_body": email_body,
        "box_colour": "primary",
        "link": reverse("events:admin_summary", kwargs={"congress_id": congress.id}),
        "link_text": "View Congress",
    }

    send_cobalt_email_with_template(to_address=congress.contact_email, context=context)


def fix_congress_normal(congress, system_account):
    """fix congress on normal date"""

    print("Fixing congress after normal delay", congress)

    results = fix_closed_congress(congress, system_account)

    email_body = f"""
                     <h1>Completed Congress with Outstanding Payments - Closed</h1>
                     <p>You are registered as the contact email address for <b>{congress}</b> on MyABF that finished
                     on {congress.end_date:%-d %B %Y}.</p>
                     <p>This congress still had outstanding payments due.<p>
                     <p>We have adjusted all outstanding amounts to regard them as paid and marked them as
                     “System adjusted”  This removes any debts still showing to players.</p>
                     <h2>There is nothing more to do</h2>
                     <br>
                     {results}
     """

    context = {
        "name": "Tournament Organiser",
        "title": f"Congress Issues Resolved - {congress}",
        "email_body": email_body,
        "box_colour": "primary",
        "link": reverse("events:admin_summary", kwargs={"congress_id": congress.id}),
        "link_text": "View Congress",
    }

    send_cobalt_email_with_template(to_address=congress.contact_email, context=context)


def fix_congress_after_extension(congress, system_account):
    """fix congress anyway after 3 months"""

    print("Fixing congress after 3 months", congress)

    results = fix_closed_congress(congress, system_account)

    email_body = f"""
                     <h1>Completed Congress with Outstanding Payments - Closed After {AUTO_FIX_REGARDLESS_MONTHS} months</h1>
                     <p>You are registered as the contact email for <b>{congress}</b> on MyABF that finished
                     on {congress.end_date:%-d %B %Y}.</p>
                     <p>This congress still had outstanding payments due.<p>
                     <p>We have adjusted all outstanding amounts to regard them as paid and marked them as
                     “System adjusted”  This removes any debts still showing to players.</p>
                     <h2>There is nothing more to do</h2>
                     <br>
                     {results}
     """

    context = {
        "name": "Tournament Organiser",
        "title": f"Congress Issues Resolved - {congress}",
        "email_body": email_body,
        "box_colour": "primary",
        "link": reverse("events:admin_summary", kwargs={"congress_id": congress.id}),
        "link_text": "View Congress",
    }

    send_cobalt_email_with_template(to_address=congress.contact_email, context=context)


class Command(BaseCommand):
    def handle(self, *args, **options):

        self.stdout.write(
            self.style.SUCCESS("Handling closed congresses with problems...")
        )

        congresses = get_completed_congresses_with_money_due()

        self.stdout.write(
            self.style.SUCCESS(f"Found {len(congresses)} congress(es) to investigate")
        )

        system_account = User.objects.get(pk=ABF_USER)

        # Go through congresses
        for congress in congresses:

            # Check if just come up for follow up
            if datetime.date.today() == congress.end_date + relativedelta(
                days=FIRST_WARNING_DAYS
            ):
                send_first_warning(congress)

            # Check if just about to be automatically fixed
            elif datetime.date.today() == congress.end_date + relativedelta(
                days=AUTO_FIX_UNLESS_OVERRIDDEN_DAYS - 1
            ):
                send_last_warning(congress)

            # Auto close
            elif (
                datetime.date.today()
                >= congress.end_date
                + relativedelta(days=AUTO_FIX_UNLESS_OVERRIDDEN_DAYS)
                and not congress.do_not_auto_close_congress
            ):
                fix_congress_normal(congress, system_account)

            # Final closure regardless
            elif (
                datetime.date.today()
                >= congress.end_date
                + relativedelta(days=AUTO_FIX_UNLESS_OVERRIDDEN_DAYS)
                and congress.do_not_auto_close_congress
            ):
                fix_congress_after_extension(congress, system_account)
