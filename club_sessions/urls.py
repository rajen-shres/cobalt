from django.urls import path

from club_sessions.club_sessions_views import sessions

app_name = "club_sessions"  # pylint: disable=invalid-name

urlpatterns = [
    path("session", sessions.new_session, name="new_session"),
]
