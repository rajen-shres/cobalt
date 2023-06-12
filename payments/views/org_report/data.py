from datetime import datetime
from django.db.models import Sum
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


def organisation_transactions_by_date_range(club, start_date, end_date):
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

    # run query
    organisation_transactions = (
        OrganisationTransaction.objects.filter(
            organisation=club,
            created_date__gte=start_datetime,
            created_date__lte=end_datetime,
        )
        .order_by("-created_date")
        .select_related("member")
    )

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


def organisation_transactions_excluding_summary_by_date_range(
    club, start_date, end_date
):
    """get transactions for a date range excluding those that can be summarised - ie events and sessions

    returns a dictionary keyed on id

    """

    # Get payments in range and summarise by event id
    start_datetime, end_datetime = start_end_date_to_datetime(start_date, end_date)

    transactions = (
        OrganisationTransaction.objects.filter(organisation=club)
        .filter(event_id__isnull=True)
        .filter(club_session_id__isnull=True)
        .filter(created_date__gte=start_datetime, created_date__lte=end_datetime)
        .select_related("member")
        .order_by("pk")
    )

    # convert to dictionary and return
    return {transaction.id: transaction for transaction in transactions}


def combined_view_events_sessions_other(club, start_date, end_date):
    """return a combined view of transactions for a date range with a summary entry for events and sessions"""

    # Get 3 different types of data
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

    # combine lists
    combined_list = events_list + sessions_list + transaction_list

    # sort on date
    combined_list.sort(key=lambda x: x[0])

    return combined_list
