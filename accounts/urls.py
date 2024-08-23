# pylint: disable=missing-module-docstring,missing-class-docstring
from django.urls import path

import accounts.views.admin
import accounts.views.api
import accounts.views.profile
import accounts.views.settings
import accounts.views.search
import accounts.views.core
import accounts.views.covid
import accounts.views.system_card

app_name = "accounts"  # pylint: disable=invalid-name

urlpatterns = [
    path("register", accounts.views.core.register_user, name="register"),
    path(
        "register/<int:system_number>/<str:email>",
        accounts.views.core.register_user,
        name="register",
    ),
    path(
        "password-reset-request",
        accounts.views.core.password_reset_request,
        name="password_reset_request",
    ),
    path("loggedout", accounts.views.core.loggedout, name="loggedout"),
    path("signin", accounts.views.core.loggedout, name="signin"),
    path(
        "search-ajax",
        accounts.views.search.search_ajax,
        name="member_search_M2M_ajax",
    ),
    path(
        "detail-ajax",
        accounts.views.search.member_detail_m2m_ajax,
        name="member_detail_m2m_ajax",
    ),
    path(
        "member-search-ajax",
        accounts.views.search.member_search_ajax,
        name="member_search_ajax",
    ),
    path(
        "system-number-search-ajax",
        accounts.views.search.system_number_search_ajax,
        name="system_number_search_ajax",
    ),
    path(
        "member-details-ajax",
        accounts.views.search.member_details_ajax,
        name="member_details_ajax",
    ),
    path(
        "change-password",
        accounts.views.core.change_password,
        name="change_password",
    ),
    path(
        "activate/<str:uidb64>/<str:token>/",
        accounts.views.core.activate,
        name="activate",
    ),
    path("profile", accounts.views.profile.profile, name="user_profile"),
    path(
        "profile-covid-htmx",
        accounts.views.covid.covid_htmx,
        name="covid_htmx",
    ),
    path(
        "profile-covid-user-confirm-htmx",
        accounts.views.covid.covid_user_confirm_htmx,
        name="covid_user_confirm_htmx",
    ),
    path(
        "profile-covid-user-exempt-htmx",
        accounts.views.covid.covid_user_exempt_htmx,
        name="covid_user_exempt_htmx",
    ),
    path("settings", accounts.views.settings.user_settings, name="user_settings"),
    path(
        "update-blurb",
        accounts.views.profile.blurb_form_upload,
        name="user_blurb",
    ),
    path(
        "update-photo",
        accounts.views.profile.picture_form_upload,
        name="user_photo",
    ),
    path(
        "password_reset/",
        accounts.views.core.html_email_reset,
        name="html_email_reset",
    ),
    path(
        "public-profile/<int:pk>/",
        accounts.views.profile.public_profile,
        name="public_profile",
    ),
    path(
        "add-team-mate",
        accounts.views.profile.add_team_mate_ajax,
        name="add_team_mate_ajax",
    ),
    path(
        "delete-team-mate",
        accounts.views.profile.delete_team_mate_ajax,
        name="delete_team_mate_ajax",
    ),
    path(
        "toggle-team-mate",
        accounts.views.profile.toggle_team_mate_ajax,
        name="toggle_team_mate_ajax",
    ),
    path(
        "admin/user-signed-up-list",
        accounts.views.admin.user_signed_up_list,
        name="user_signed_up_list",
    ),
    path(
        "delete-photo",
        accounts.views.profile.delete_photo,
        name="delete_photo",
    ),
    path(
        "search/member-search",
        accounts.views.search.member_search_htmx,
        name="member_search_htmx",
    ),
    path(
        "search/system-number-search",
        accounts.views.search.system_number_search_htmx,
        name="system_number_search_htmx",
    ),
    path(
        "search/member-match",
        accounts.views.search.member_match_htmx,
        name="member_match_htmx",
    ),
    path(
        "search/member-match-summary",
        accounts.views.search.member_match_summary_htmx,
        name="member_match_summary_htmx",
    ),
    path(
        "developer/settings",
        accounts.views.settings.developer_settings_htmx,
        name="developer_settings_htmx",
    ),
    path(
        "developer/settings-delete-token",
        accounts.views.settings.developer_settings_delete_token_htmx,
        name="developer_settings_delete_token_htmx",
    ),
    path(
        "admin/toggle-user-is-active",
        accounts.views.admin.admin_toggle_user_is_active,
        name="admin_toggle_user_is_active",
    ),
    path(
        "admin/mark-user-deceased",
        accounts.views.admin.admin_mark_user_deceased,
        name="admin_mark_user_deceased",
    ),
    path(
        "delete-device",
        accounts.views.api.delete_fcm_device_ajax,
        name="delete_fcm_device_ajax",
    ),
    path(
        "delete-session",
        accounts.views.api.delete_session_ajax,
        name="delete_session_token_ajax",
    ),
    path(
        "unregistered-preferences/<str:identifier>",
        accounts.views.settings.unregistered_user_settings,
        name="unregistered_settings",
    ),
    path(
        "system-card/<int:user_id>/<str:system_card_name>",
        accounts.views.system_card.system_card_view,
        name="system_card_view",
    ),
    path(
        "system-card-edit/<str:system_card_name>",
        accounts.views.system_card.system_card_edit,
        name="system_card_edit",
    ),
    path(
        "create-pdf-system-card/<str:system_card_name>",
        accounts.views.system_card.create_pdf_system_card,
        name="create_pdf_system_card",
    ),
]
