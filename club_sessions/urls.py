from django.urls import path

from club_sessions.club_sessions_views import sessions

app_name = "club_sessions"  # pylint: disable=invalid-name

urlpatterns = [
    path("new-session/<int:club_id>", sessions.new_session, name="new_session"),
    path("session/<int:session_id>", sessions.manage_session, name="manage_session"),
    path("session/settings", sessions.tab_settings_htmx, name="tab_settings_htmx"),
    path(
        "session/uploads",
        sessions.tab_import_htmx,
        name="tab_import_htmx",
    ),
    path(
        "session/uploads-file",
        sessions.import_file_upload_htmx,
        name="session_import_file_upload_htmx",
    ),
    path(
        "session/details",
        sessions.tab_session_htmx,
        name="tab_session_htmx",
    ),
    path(
        "session/edit-session-entry",
        sessions.edit_session_entry_htmx,
        name="edit_session_entry_htmx",
    ),
    path(
        "session/edit-session-entry-extras",
        sessions.edit_session_entry_extras_htmx,
        name="edit_session_entry_extras_htmx",
    ),
    path(
        "session/edit-session-entry-change-payment-method",
        sessions.change_payment_method_htmx,
        name="session_entry_change_payment_method_htmx",
    ),
    path(
        "session/edit-session-entry-change-paid-amount",
        sessions.change_paid_amount_status_htmx,
        name="session_entry_change_paid_amount_htmx",
    ),
    path(
        "session/edit-session-totals",
        sessions.session_totals_htmx,
        name="session_entry_session_totals_htmx",
    ),
    path(
        "session/add-misc-payment",
        sessions.add_misc_payment_htmx,
        name="session_add_misc_payment_htmx",
    ),
]
