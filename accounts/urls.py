# pylint: disable=missing-module-docstring,missing-class-docstring
from django.urls import path

# from django.http import HttpResponse
from . import views

app_name = "accounts"  # pylint: disable=invalid-name

urlpatterns = [
    path("register", views.register, name="register"),
    path(
        "password-reset-request",
        views.password_reset_request,
        name="password_reset_request",
    ),
    path("loggedout", views.loggedout, name="loggedout"),
    path("signin", views.loggedout, name="signin"),
    path("search-ajax", views.search_ajax, name="member_search_M2M_ajax"),
    path("detail-ajax", views.member_detail_m2m_ajax, name="member_detail_m2m_ajax"),
    path("member-search-ajax", views.member_search_ajax, name="member_search_ajax"),
    path(
        "system-number-search-ajax",
        views.system_number_search_ajax,
        name="system_number_search_ajax",
    ),
    path("member-details-ajax", views.member_details_ajax, name="member_details_ajax"),
    path("change-password", views.change_password, name="change_password"),
    path("activate/<str:uidb64>/<str:token>/", views.activate, name="activate"),
    path("profile", views.profile, name="user_profile"),
    path("profile-covid-htmx", views.covid_htmx, name="covid_htmx"),
    path(
        "profile-covid-user-confirm-htmx",
        views.covid_user_confirm_htmx,
        name="covid_user_confirm_htmx",
    ),
    path(
        "profile-covid-user-exempt-htmx",
        views.covid_user_exempt_htmx,
        name="covid_user_exempt_htmx",
    ),
    path("settings", views.user_settings, name="user_settings"),
    path("update-blurb", views.blurb_form_upload, name="user_blurb"),
    path("update-photo", views.picture_form_upload, name="user_photo"),
    path("password_reset/", views.html_email_reset, name="html_email_reset"),
    path("public-profile/<int:pk>/", views.public_profile, name="public_profile"),
    path("add-team-mate", views.add_team_mate_ajax, name="add_team_mate_ajax"),
    path("delete-team-mate", views.delete_team_mate_ajax, name="delete_team_mate_ajax"),
    path("toggle-team-mate", views.toggle_team_mate_ajax, name="toggle_team_mate_ajax"),
    path("user-signed-up-list", views.user_signed_up_list, name="user_signed_up_list"),
    path("delete-photo", views.delete_photo, name="delete_photo"),
    path("search/member-search", views.member_search_htmx, name="member_search_htmx"),
    path(
        "search/system-number-search",
        views.system_number_search_htmx,
        name="system_number_search_htmx",
    ),
    path("search/member-match", views.member_match_htmx, name="member_match_htmx"),
    path(
        "search/member-match-summary",
        views.member_match_summary_htmx,
        name="member_match_summary_htmx",
    ),
    path(
        "developer/settings",
        views.developer_settings_htmx,
        name="developer_settings_htmx",
    ),
    path(
        "developer/settings-delete-token",
        views.developer_settings_delete_token_htmx,
        name="developer_settings_delete_token_htmx",
    ),
    path(
        "admin/toggle-user-is-active",
        views.admin_toggle_user_is_active,
        name="admin_toggle_user_is_active",
    ),
]
