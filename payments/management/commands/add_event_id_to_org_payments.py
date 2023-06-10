""" Temp script to add event id to org payments as this was not initially captured """

from django.core.management.base import BaseCommand
from django.utils.html import escape

from events.models import Event
from payments.models import OrganisationTransaction


def _sort_description(description):
    """modify description"""

    # Refund will be like:
    #   Refund to Peter Evans (ABF: 213527) for QBA Butler Pairs

    # Payment will be like:
    #   Festival Thursday Matchpoint Swiss Pairs @ REALBRIDGE - Manda Labuschagne (ABF: 703699)
    # or
    #   Festival Thursday Matchpoint Swiss Pairs @ REALBRIDGE - TBA

    # See if this is a refund
    if description.find("Refund to") == 0:
        loc = description.find(") for ")
        if loc > 0:
            loc = loc + 6
            description = description[loc:]
    else:
        # This is a payment
        # Strip name and ABF No if we have them
        loc = description.rfind(" - ")
        if description[loc:].find("(ABF:") >= 0:
            description = description[:loc]

        # Strip TBA - doesn't have (ABF:
        if description[loc:].find("TBA") >= 0:
            description = description[:loc]

    # Handle &lt; etc
    description = escape(description)

    # Put back quote - dunno why
    description = description.replace("&#x27;", "'")

    return description


def _add_hacks():
    """analyse changed names and moved to other orgs. Read from a file"""

    for line in open("/tmp/hacks"):
        org_id = int(line.split()[0])
        description = " ".join(line.split()[1:]).strip()

        print("\n", org_id, description)

        # Try for similar names
        events = Event.objects.filter(
            event_name__startswith=description[:10],
            congress__congress_master__org_id=org_id,
        )

        for event in events:
            if event.description:
                print(f"    Possible match: {event.description}")

    # description = _sort_description(tran.description)


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--hacks",
            action="store_true",
            help="Use specific handling of known cases",
        )

        parser.add_argument(
            "--add_hacks",
            action="store_true",
            help="Help to find the required hard codings",
        )

        parser.add_argument(
            "--print_hacks",
            action="store_true",
            help="Print data for add_hacks. Run: ./manage.py add_event_id_to_org_payments --print_hacks> /tmp/hacks-raw; cat /tmp/hacks-raw | sort -u > /tmp/hacks",
        )

    def handle(self, *args, **options):

        # Add hacks is to help us identify why this doesn't go through normally - org or name change
        if options["add_hacks"]:
            return _add_hacks()

        # Get all payments for events
        trans = OrganisationTransaction.objects.filter(
            type__in=["Entry to an event", "Refund"], event_id__isnull=True
        )

        max_count = trans.count()
        # print("##########################################################")
        # print(f"# Found {max_count} items")
        # print("##########################################################")

        for count, tran in enumerate(trans, start=1):
            description = _sort_description(tran.description)
            created_date = tran.created_date.date()

            # org id
            org_id = tran.organisation_id

            # Specific hacks - names have changed etc. Only use the seconds time we run
            if options["hacks"]:
                if description == "Western Seniors Pairs" and org_id == 7:
                    org_id = 26

            # Try to match an event
            events = Event.objects.filter(
                event_name=description, congress__congress_master__org_id=org_id
            )

            if not options["print_hacks"]:
                print(f"{count}/{max_count}")

            if events.count() == 0:

                if options["print_hacks"]:
                    # For the add_hacks use this. Then run:
                    #     ./manage.py add_event_id_to_org_payments --print_hacks > /tmp/hacks-raw
                    #     cat /tmp/hacks-raw | sort -u > /tmp/hacks
                    print(f"{org_id} {description}")

                else:
                    # For normal use this
                    print(
                        f"\nNO MATCH ++++++ {org_id} {tran.organisation} - '{description}' - {created_date}"
                    )

            elif events.count() == 1:
                print(f"\nUnique match for: {org_id} - {description} - {created_date}")
                tran.event_id = events[0].id
                tran.save()

            elif events.count() > 1:
                print(
                    f"\nMultiple matches for: {org_id} - {description} - {created_date}"
                )
                closest = None
                closest_days = 99999
                for event in events:
                    print(f"-- {event} - {event.denormalised_start_date}")
                    try:
                        diff = abs((created_date - event.denormalised_start_date).days)
                    except TypeError:
                        # Not sure why
                        print("---------------> TypeError")
                        diff = 99999999
                    if diff < closest_days:
                        closest_days = diff
                        closest = event.id
                print(f"Matched to {closest}")
                tran.event_id = closest
                tran.save()
