# pylint: disable=missing-module-docstring,missing-class-docstring
from django.urls import path

# from django.http import HttpResponse
import accounts.accounts_views.admin
import accounts.accounts_views.api
import accounts.accounts_views.core
import accounts.accounts_views.covid
import accounts.accounts_views.profile
import accounts.accounts_views.search
import accounts.accounts_views.settings

app_name = "accounts"  # pylint: disable=invalid-name

urlpatterns = [
    path("register", accounts.accounts_views.core.register_user, name="register"),
    path(
        "password-reset-request",
        accounts.accounts_views.core.password_reset_request,
        name="password_reset_request",
    ),
    path("loggedout", accounts.accounts_views.core.loggedout, name="loggedout"),
    path("signin", accounts.accounts_views.core.loggedout, name="signin"),
    path(
        "search-ajax",
        accounts.accounts_views.search.search_ajax,
        name="member_search_M2M_ajax",
    ),
    path(
        "detail-ajax",
        accounts.accounts_views.search.member_detail_m2m_ajax,
        name="member_detail_m2m_ajax",
    ),
    path(
        "member-search-ajax",
        accounts.accounts_views.search.member_search_ajax,
        name="member_search_ajax",
    ),
    path(
        "system-number-search-ajax",
        accounts.accounts_views.search.system_number_search_ajax,
        name="system_number_search_ajax",
    ),
    path(
        "member-details-ajax",
        accounts.accounts_views.search.member_details_ajax,
        name="member_details_ajax",
    ),
    path(
        "change-password",
        accounts.accounts_views.core.change_password,
        name="change_password",
    ),
    path(
        "activate/<str:uidb64>/<str:token>/",
        accounts.accounts_views.core.activate,
        name="activate",
    ),
    path("profile", accounts.accounts_views.profile.profile, name="user_profile"),
    path(
        "profile-covid-htmx",
        accounts.accounts_views.covid.covid_htmx,
        name="covid_htmx",
    ),
    path(
        "profile-covid-user-confirm-htmx",
        accounts.accounts_views.covid.covid_user_confirm_htmx,
        name="covid_user_confirm_htmx",
    ),
    path(
        "profile-covid-user-exempt-htmx",
        accounts.accounts_views.covid.covid_user_exempt_htmx,
        name="covid_user_exempt_htmx",
    ),
    path(
        "settings", accounts.accounts_views.settings.user_settings, name="user_settings"
    ),
    path(
        "update-blurb",
        accounts.accounts_views.profile.blurb_form_upload,
        name="user_blurb",
    ),
    path(
        "update-photo",
        accounts.accounts_views.profile.picture_form_upload,
        name="user_photo",
    ),
    path(
        "password_reset/",
        accounts.accounts_views.core.html_email_reset,
        name="html_email_reset",
    ),
    path(
        "public-profile/<int:pk>/",
        accounts.accounts_views.profile.public_profile,
        name="public_profile",
    ),
    path(
        "add-team-mate",
        accounts.accounts_views.profile.add_team_mate_ajax,
        name="add_team_mate_ajax",
    ),
    path(
        "delete-team-mate",
        accounts.accounts_views.profile.delete_team_mate_ajax,
        name="delete_team_mate_ajax",
    ),
    path(
        "toggle-team-mate",
        accounts.accounts_views.profile.toggle_team_mate_ajax,
        name="toggle_team_mate_ajax",
    ),
    path(
        "user-signed-up-list",
        accounts.accounts_views.admin.user_signed_up_list,
        name="user_signed_up_list",
    ),
    path(
        "delete-photo",
        accounts.accounts_views.profile.delete_photo,
        name="delete_photo",
    ),
    path(
        "search/member-search",
        accounts.accounts_views.search.member_search_htmx,
        name="member_search_htmx",
    ),
    path(
        "search/system-number-search",
        accounts.accounts_views.search.system_number_search_htmx,
        name="system_number_search_htmx",
    ),
    path(
        "search/member-match",
        accounts.accounts_views.search.member_match_htmx,
        name="member_match_htmx",
    ),
    path(
        "search/member-match-summary",
        accounts.accounts_views.search.member_match_summary_htmx,
        name="member_match_summary_htmx",
    ),
    path(
        "developer/settings",
        accounts.accounts_views.settings.developer_settings_htmx,
        name="developer_settings_htmx",
    ),
    path(
        "developer/settings-delete-token",
        accounts.accounts_views.settings.developer_settings_delete_token_htmx,
        name="developer_settings_delete_token_htmx",
    ),
    path(
        "admin/toggle-user-is-active",
        accounts.accounts_views.admin.admin_toggle_user_is_active,
        name="admin_toggle_user_is_active",
    ),
    path(
        "delete-device",
        accounts.accounts_views.api.delete_fcm_device_ajax,
        name="delete_fcm_device_ajax",
    ),
]
