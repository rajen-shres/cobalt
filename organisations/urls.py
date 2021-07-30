# pylint: disable=missing-module-docstring,missing-class-docstring
from django.urls import path
from . import views, ajax

app_name = "organisations"  # pylint: disable=invalid-name

urlpatterns = [
    path("org-search-ajax", ajax.org_search_ajax, name="org_search_ajax"),
    path("org-detail-ajax", ajax.org_detail_ajax, name="org_detail_ajax"),
    path(
        "admin/club-details", ajax.get_club_details_ajax, name="get_club_details_ajax"
    ),
    path(
        "admin/club-name-search",
        ajax.club_name_search_ajax,
        name="club_name_search_ajax",
    ),
    path("edit/<int:org_id>", views.org_edit, name="org_edit"),
    path("admin/add-club", views.admin_add_club, name="admin_add_club"),
    path("admin/list-clubs", views.admin_list_clubs, name="admin_list_clubs"),
    path(
        "admin/club-rbac/<int:club_id>", views.admin_club_rbac, name="admin_club_rbac"
    ),
    path(
        "admin/club-rbac-basic/<int:club_id>",
        views.admin_club_rbac_add_basic,
        name="admin_club_rbac_add_basic",
    ),
    path(
        "admin/club-rbac-advanced/<int:club_id>",
        views.admin_club_rbac_add_advanced,
        name="admin_club_rbac_add_advanced",
    ),
    path(
        "admin/club-rbac-basic-to-advanced/<int:club_id>",
        views.admin_club_rbac_convert_basic_to_advanced,
        name="admin_club_rbac_convert_basic_to_advanced",
    ),
    path(
        "admin/club-rbac-advanced-to-basic/<int:club_id>",
        views.admin_club_rbac_convert_advanced_to_basic,
        name="admin_club_rbac_convert_advanced_to_basic",
    ),
    path("club-menu/<int:club_id>", views.club_menu, name="club_menu"),
    path(
        "admin/access-basic/delete-user/<int:club_id>/<int:user_id>",
        views.club_admin_access_basic_delete_user_htmx,
        name="club_admin_access_basic_delete_user_htmx",
    ),
]
