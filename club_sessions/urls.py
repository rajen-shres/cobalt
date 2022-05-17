from django.urls import path

from club_sessions.club_sessions_views import sessions

app_name = "club_sessions"  # pylint: disable=invalid-name

urlpatterns = [
    path("new-session/<int:club_id>", sessions.new_session, name="new_session"),
    path("session/<int:session_id>", sessions.manage_session, name="manage_session"),
    path(
        "session/settings", sessions.tab_edit_session_htmx, name="tab_edit_session_htmx"
    ),
    path(
        "session/details",
        sessions.tab_session_details_htmx,
        name="tab_session_details_htmx",
    ),
]
