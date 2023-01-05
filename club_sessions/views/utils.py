from club_sessions.models import Session


def get_session_statistics():
    """
    System stats for club_sessions
    """

    return {
        "total_sessions": Session.objects.count(),
        "distinct_clubs": Session.objects.distinct(
            "session_type__organisation"
        ).count(),
    }
