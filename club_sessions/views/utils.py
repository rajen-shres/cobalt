from django.db.models import Sum

from club_sessions.models import Session, SessionEntry
from cobalt.settings import BRIDGE_CREDITS


def get_session_statistics():
    """
    System stats for club_sessions
    """

    total_payments_query = SessionEntry.objects.filter(is_paid=True)
    total_payments = total_payments_query.aggregate(Sum("fee"))
    total_bridge_credits = total_payments_query.filter(
        payment_method__payment_method=BRIDGE_CREDITS
    ).aggregate(Sum("fee"))

    return {
        "total_sessions": Session.objects.count(),
        "distinct_clubs": Session.objects.distinct(
            "session_type__organisation"
        ).count(),
        "total_payments": total_payments["fee__sum"],
        "total_bridge_credits": total_bridge_credits["fee__sum"],
    }
