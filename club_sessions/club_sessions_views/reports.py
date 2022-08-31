from decimal import Decimal

from django.shortcuts import render

from club_sessions.club_sessions_views.decorators import user_is_club_director
from club_sessions.club_sessions_views.sessions import load_session_entry_static


@user_is_club_director()
def reconciliation_htmx(request, club, session):
    """Basic report of a session"""

    # Load starting data
    (
        session_entries,
        mixed_dict,
        session_fees,
        membership_type_dict,
    ) = load_session_entry_static(session, club)

    # Build summary around session_fees - start by building structure
    print(session_fees)
    summary_table = {}
    column_headings = []

    # We want the column names so use the Guest row which is always present
    column_headings = [payment_method for payment_method in session_fees["Guest"]]

    # Now build the other rows
    membership_types = list(session_fees.keys()) + ["Totals"]
    for membership_type in membership_types:

        summary_table[membership_type] = {}

        for payment_method in session_fees[membership_type]:
            summary_table[membership_type][payment_method] = {}
            # Handle membership and payment eg. Guest Cash
            summary_table[membership_type][payment_method][
                "default_fee"
            ] = session_fees[membership_type][payment_method]
            summary_table[membership_type][payment_method]["fee"] = Decimal(0.0)
            summary_table[membership_type][payment_method]["paid"] = Decimal(0.0)

            # Include totals
            summary_table["Totals"][payment_method] = {}
            summary_table["Totals"][payment_method]["fee"] = Decimal(0.0)
            summary_table["Totals"][payment_method]["paid"] = Decimal(0.0)

        # Also create a total for the row, eg total for Guests for all payment types
        summary_table[membership_type]["row_total"] = {}
        summary_table[membership_type]["row_total"]["fee"] = Decimal(0.0)
        summary_table[membership_type]["row_total"]["paid"] = Decimal(0.0)

    # Add a bottom line total by payment type
    # summary_table["Totals"] = {}

    # Add the session data in
    for session_entry in session_entries:

        # Skip sit outs and directors
        if session_entry.system_number not in [1, -1]:

            membership_type = membership_type_dict[session_entry.system_number]
            payment_method = session_entry.payment_method.payment_method

            # This cell
            summary_table[membership_type][payment_method][
                "paid"
            ] += session_entry.amount_paid
            summary_table[membership_type][payment_method]["fee"] += session_entry.fee

            # Row totals
            summary_table[membership_type]["row_total"][
                "paid"
            ] += session_entry.amount_paid
            summary_table[membership_type]["row_total"]["fee"] += session_entry.fee

            # Column totals
            summary_table["Totals"][payment_method]["paid"] += session_entry.amount_paid
            summary_table["Totals"][payment_method]["fee"] += session_entry.fee

    print(summary_table)
    for membership_type in summary_table:
        print("---", payment_method)
        for payment_method in summary_table[membership_type]:
            print(summary_table[membership_type][payment_method])

    return render(
        request,
        "club_sessions/reports/reconciliation.html",
        {
            "club": club,
            "session": session,
            "session_entries": session_entries,
            "summary_table": summary_table,
            "column_headings": column_headings,
        },
    )
