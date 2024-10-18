from datetime import datetime

from django.db.models import Sum, Q
from django.forms import model_to_dict

from club_sessions.models import Session
from events.models import Event
from payments.models import OrganisationTransaction
from payments.views.org_report.utils import (
    start_end_date_to_datetime,
    format_date_helper,
    date_to_datetime_midnight,
    derive_counterparty,
)


def session_names_for_date_range(club, start_datetime, end_datetime):
    """return a dict of session_id to session name for a given date range"""

    # Get session ids
    session_ids = (
        OrganisationTransaction.objects.filter(
            organisation=club,
            created_date__gte=start_datetime,
            created_date__lte=end_datetime,
        )
        .filter(club_session_id__isnull=False)
        .values_list("club_session_id", flat=True)
        .distinct("club_session_id")
    )

    # Get session names
    session_names = Session.objects.filter(pk__in=session_ids)
    return {session_name.id: session_name.description for session_name in session_names}


def event_names_for_date_range(club, start_datetime, end_datetime):
    """return a dict of event_id to event name for a given date range"""

    # Get event ids
    event_ids = (
        OrganisationTransaction.objects.filter(
            organisation=club,
            created_date__gte=start_datetime,
            created_date__lte=end_datetime,
        )
        .filter(event_id__isnull=False)
        .values_list("event_id", flat=True)
        .distinct("event_id")
    )

    # Get event names and start date
    event_names = (
        Event.objects.filter(id__in=event_ids)
        .select_related("congress")
        .values("id", "event_name", "congress__name", "denormalised_start_date")
    )

    return {
        event_name["id"]: {
            "congress_name": event_name["congress__name"],
            "event_name": event_name["event_name"],
            "start_date": event_name["denormalised_start_date"],
        }
        for event_name in event_names
    }


def congress_names_for_date_range(club, start_datetime, end_datetime):
    """return a dict of event_id to congress name for a given date range. Also returns a dict of event_id to congress_id

    We can't map things directly to congresses, only to events
    """

    # Get event ids
    event_ids = (
        OrganisationTransaction.objects.filter(
            organisation=club,
            created_date__gte=start_datetime,
            created_date__lte=end_datetime,
        )
        .filter(event_id__isnull=False)
        .values_list("event_id", flat=True)
        .distinct("event_id")
    )

    # Get congress names and start date, as well as congress_id and event_id
    congress_names = (
        Event.objects.filter(id__in=event_ids)
        .select_related("congress")
        .values("id", "congress_id", "congress__name", "congress__start_date")
    )

    print(congress_names)

    congress_name_dict = {}

    for congress_name in congress_names:
        congress_name_dict[congress_name["congress_id"]] = {
            "congress_id": congress_name["congress_id"],
            "congress_name": congress_name["congress__name"],
            "start_date": congress_name["congress__start_date"],
        }

    event_to_congress_dict = {}
    for congress_name in congress_names:
        event_to_congress_dict[congress_name["id"]] = congress_name["congress_id"]

    return congress_name_dict, event_to_congress_dict


def sessions_and_payments_by_date_range(club, start_date, end_date):
    """ " Get session and payments in this date range

    returns a dictionary of sessions keyed on id and payment mapping dictionary also keyed on id

    """

    sessions_in_range = (
        Session.objects.filter(session_type__organisation=club)
        .filter(session_date__gte=start_date, session_date__lte=end_date)
        .order_by("session_date")
    )

    # convert to dictionary
    sessions_in_range_dict = {
        session_in_range.id: session_in_range for session_in_range in sessions_in_range
    }

    # Get ids of sessions
    sessions_list = sessions_in_range.values_list("id", flat=True)

    # Get payments
    session_payments = (
        OrganisationTransaction.objects.filter(organisation=club)
        .filter(club_session_id__in=sessions_list)
        .values("club_session_id")
        .annotate(amount=Sum("amount"))
    )

    payments_dict = {
        session_payment["club_session_id"]: session_payment["amount"]
        for session_payment in session_payments
    }

    return sessions_in_range_dict, payments_dict


def _organisation_transactions_by_date_range_augment_data(
    organisation_transaction, session_names_dict, event_names_dict
):
    """Add extra values to the queryset of organisation transactions"""

    # Session name
    if organisation_transaction.club_session_id:
        try:
            organisation_transaction.club_session_name = session_names_dict[
                organisation_transaction.club_session_id
            ]
        except KeyError:
            organisation_transaction.club_session_name = (
                "Not found - session may be deleted"
            )
    else:
        organisation_transaction.club_session_name = ""

    # Event name
    if organisation_transaction.event_id:
        organisation_transaction.event_name = f"{event_names_dict[organisation_transaction.event_id]['congress_name']} - {event_names_dict[organisation_transaction.event_id]['event_name']}"
    else:
        organisation_transaction.event_name = ""

    # counterparty
    organisation_transaction.counterparty = derive_counterparty(
        organisation_transaction
    )

    # Date
    organisation_transaction.formatted_date = format_date_helper(
        organisation_transaction.created_date
    )

    return organisation_transaction


def organisation_transactions_by_date_range(
    club,
    start_date,
    end_date,
    description_search=None,
    augment_data=True,
    transaction_type=None,
):
    """get the data for both the CSV and Excel downloads

    Returns: queryset of OrganisationTransactions in range with augmented fields for -
                club_session_id: id of Session
                club_session_name: Session.description
                event_id: Event.id
                event_name: Congress.name and Event.event_name as string
                counterparty: string for counterparty
                formatted_date: pre-formatted date of transaction

    """

    # Convert dates to date times
    start_datetime, end_datetime = start_end_date_to_datetime(start_date, end_date)

    # JPG cleanup
    # # run query
    # organisation_transactions = (
    #     OrganisationTransaction.objects.filter(
    #         organisation=club,
    #         created_date__gte=start_datetime,
    #         created_date__lte=end_datetime,
    #     )
    #     .order_by("-created_date")
    #     .select_related("member")
    # )

    # build the base query
    organisation_transactions = OrganisationTransaction.objects.filter(
        organisation=club,
        created_date__gte=start_datetime,
        created_date__lte=end_datetime,
    )

    if transaction_type and transaction_type != "all":
        organisation_transactions = organisation_transactions.filter(
            type=transaction_type,
        )

    organisation_transactions = organisation_transactions.order_by(
        "-created_date"
    ).select_related("member")

    # filter if required - note we also search for first name and last name as well as description
    if description_search:
        organisation_transactions = organisation_transactions.filter(
            Q(description__icontains=description_search)
            | Q(member__first_name__icontains=description_search)
            | Q(member__last_name__icontains=description_search)
        )

    if not augment_data:
        # for the web display, don't augment data
        return organisation_transactions

    # Get session and event name mappings
    session_names_dict = session_names_for_date_range(
        club, start_datetime, end_datetime
    )
    event_names_dict = event_names_for_date_range(club, start_datetime, end_datetime)

    # Augment data
    for organisation_transaction in organisation_transactions:
        organisation_transaction = (
            _organisation_transactions_by_date_range_augment_data(
                organisation_transaction, session_names_dict, event_names_dict
            )
        )

    return organisation_transactions


def club_membership_summary_by_date_range(club, start_date, end_date):
    """Returns the total of club membership transactions within a date range.
    Will return None if no membership transactions, 0 if balanced out
    """

    start_datetime, end_datetime = start_end_date_to_datetime(start_date, end_date)

    return OrganisationTransaction.objects.filter(
        organisation=club,
        created_date__gte=start_datetime,
        created_date__lte=end_datetime,
        type="Club Membership",
    ).aggregate(total=Sum("amount"))["total"]


def event_payments_summary_by_date_range(club, start_date, end_date):
    """return summary of event payments within a date range.

    returns a dictionary with key: event_id
                              values: dictionary
                                      congress_name
                                      event_name
                                      start_date
                                      amount
                                      amount_outside_range (payments for event not in date range)

    """

    # Get payments in range and summarise by event id
    start_datetime, end_datetime = start_end_date_to_datetime(start_date, end_date)

    event_payments = (
        OrganisationTransaction.objects.filter(organisation=club)
        .filter(event_id__isnull=False)
        .filter(created_date__gte=start_datetime, created_date__lte=end_datetime)
        .values("event_id")
        .annotate(amount=Sum("amount"))
    )

    # get event names mapping
    event_names_dict = event_names_for_date_range(club, start_datetime, end_datetime)

    # We have payments within the date range, we also want total payments for events to highlight anything missed
    total_event_payments = (
        OrganisationTransaction.objects.filter(organisation=club)
        .filter(event_id__in=event_names_dict.keys())
        .values("event_id")
        .annotate(amount=Sum("amount"))
    )

    # turn into a dictionary
    total_event_payments_dict = {
        total_event_payment["event_id"]: total_event_payment["amount"]
        for total_event_payment in total_event_payments
    }

    # Now combine it all
    event_payment_dict = {}
    for event_payment in event_payments:
        this_id = event_payment["event_id"]
        event_payment_dict[this_id] = {
            "id": this_id,
            "amount": event_payment["amount"],
            "congress_name": event_names_dict[this_id]["congress_name"],
            "event_name": event_names_dict[this_id]["event_name"],
            "start_date": event_names_dict[this_id]["start_date"],
            "amount_outside_range": total_event_payments_dict[this_id]
            - event_payment["amount"],
        }

    # We can't select on start date order as we use an annotation, so sort it now by date
    sorted_index = sorted(
        event_payment_dict, key=lambda x: event_payment_dict[x]["start_date"]
    )

    return {index: event_payment_dict[index] for index in sorted_index}


def congress_payments_summary_by_date_range(club, start_date, end_date):
    """return summary of congress payments within a date range.

    returns a dictionary with key: congress_id
                              values: dictionary
                                      congress_name
                                      start_date
                                      amount
                                      amount_outside_range (payments for event not in date range)

    """

    # Get payments in range and summarise by event id - we can't do it by congress_id in one step
    start_datetime, end_datetime = start_end_date_to_datetime(start_date, end_date)

    event_payments = (
        OrganisationTransaction.objects.filter(organisation=club)
        .filter(event_id__isnull=False)
        .filter(created_date__gte=start_datetime, created_date__lte=end_datetime)
        .values("event_id")
        .annotate(amount=Sum("amount"))
    )

    # get congress names mapping
    congress_name_dict, event_to_congress_dict = congress_names_for_date_range(
        club, start_datetime, end_datetime
    )

    # We have payments within the date range, we also want total payments for events to highlight anything missed
    total_event_payments = (
        OrganisationTransaction.objects.filter(organisation=club)
        .filter(event_id__in=event_to_congress_dict.keys())
        .values("event_id")
        .annotate(amount=Sum("amount"))
    )

    # turn into a dictionary
    total_event_payments_dict = {
        total_event_payment["event_id"]: total_event_payment["amount"]
        for total_event_payment in total_event_payments
    }

    # Now combine it all
    congress_payment_dict = {}
    # One congress can have multiple events. Go through at the event level
    for event_payment in event_payments:
        # get congress id for this event
        congress_id = event_to_congress_dict[event_payment["event_id"]]
        # If already in dictionary then add this event to the totals
        if congress_id in congress_payment_dict:
            congress_payment_dict[congress_id]["amount"] += event_payment["amount"]
            congress_payment_dict[congress_id][
                "amount_outside_range"
            ] += total_event_payments_dict[event_payment["event_id"]]
            congress_payment_dict[congress_id]["amount_outside_range"] -= event_payment[
                "amount"
            ]
        # if not in dictionary, then add it
        else:
            congress_payment_dict[congress_id] = {
                "id": congress_id,
                "amount": event_payment["amount"],
                "congress_name": congress_name_dict[congress_id]["congress_name"],
                "start_date": congress_name_dict[congress_id]["start_date"],
                "amount_outside_range": total_event_payments_dict[
                    event_payment["event_id"]
                ]
                - event_payment["amount"],
            }

    # We can't select on start date order as we use an annotation, so sort it now by date
    sorted_index = sorted(
        congress_payment_dict, key=lambda x: congress_payment_dict[x]["start_date"]
    )

    return {index: congress_payment_dict[index] for index in sorted_index}


def organisation_transactions_excluding_summary_by_date_range(
    club, start_date, end_date
):
    """get transactions for a date range excluding those that can be summarised - ie events, sessions and membership

    returns a dictionary keyed on id

    """

    # Get payments in range and summarise by event id
    start_datetime, end_datetime = start_end_date_to_datetime(start_date, end_date)

    transactions = (
        OrganisationTransaction.objects.filter(organisation=club)
        .filter(event_id__isnull=True)
        .filter(club_session_id__isnull=True)
        .filter(created_date__gte=start_datetime, created_date__lte=end_datetime)
        .exclude(type="Club Membership")
        .select_related("member")
        .order_by("pk")
    )

    # convert to dictionary and return
    return {transaction.id: transaction for transaction in transactions}


def combined_view_events_sessions_other(club, start_date, end_date):
    """return a combined view of transactions for a date range with a summary entry for events and sessions"""

    # Get 3 different types of data, membership handled separately
    events = event_payments_summary_by_date_range(club, start_date, end_date)
    sessions, payments_dict = sessions_and_payments_by_date_range(
        club, start_date, end_date
    )
    transactions = organisation_transactions_excluding_summary_by_date_range(
        club, start_date, end_date
    )

    # These are all dictionaries keyed on id, we want a list ordered by date

    # events to list
    sorted_index = sorted(events, key=lambda x: events[x]["start_date"])

    # list of tuples (datetime, values). We need to change the date to a datetime as well
    events_list = []
    for index in sorted_index:

        data = {
            "formatted_date": date_to_datetime_midnight(
                events[index]["start_date"]
            ).__str__()[:-6],
            "unformatted_date": date_to_datetime_midnight(events[index]["start_date"]),
            "event_id": index,
            "event_name": f"{events[index]['congress_name']} - {events[index]['event_name']}",
            "description": f"{events[index]['congress_name']} - {events[index]['event_name']}",
            "amount_outside_range": events[index]["amount_outside_range"],
            "amount": events[index]["amount"],
            "type": "Event Entry",
        }
        events_list.append(
            (date_to_datetime_midnight(events[index]["start_date"]), data)
        )

    # sessions to list
    sorted_index = sorted(sessions, key=lambda x: sessions[x].session_date)

    # list of tuples (datetime, values). We need to change the date to a datetime as well
    sessions_list = []
    for index in sorted_index:
        data = {
            "formatted_date": date_to_datetime_midnight(
                sessions[index].session_date
            ).__str__()[:-6],
            "unformatted_date": date_to_datetime_midnight(sessions[index].session_date),
            "club_session_id": index,
            "club_session_name": sessions[index].description,
            "description": sessions[index].description,
            "amount": payments_dict.get(index, "No Payments"),
            "type": "Club Payment",
        }
        sessions_list.append(
            (date_to_datetime_midnight(sessions[index].session_date), data)
        )

    # transactions to list
    sorted_index = sorted(transactions, key=lambda x: transactions[x].created_date)

    # list of tuples (datetime, values)
    transaction_list = []
    for index in sorted_index:
        data = model_to_dict(transactions[index])
        data["counterparty"] = derive_counterparty(transactions[index])
        data["formatted_date"] = format_date_helper(transactions[index].created_date)
        transaction_list.append((transactions[index].created_date, data))

    # get the club summary
    club_membership_total = club_membership_summary_by_date_range(
        club, start_date, end_date
    )
    if club_membership_total:
        membership_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        club_membership = [
            (
                date_to_datetime_midnight(membership_date),
                {
                    "unformatted_date": membership_date,
                    "counterparty": "Club Members",
                    "type": "Club Membership",
                    "description": "Total Club Membership Fees",
                    "amount": club_membership_total,
                },
            )
        ]
    else:
        club_membership = []

    # combine lists
    combined_list = events_list + sessions_list + transaction_list + club_membership

    # sort on date
    combined_list.sort(key=lambda x: x[0])

    return combined_list
