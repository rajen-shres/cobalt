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
    path("edit/<int:org_id>", views.org_edit, name="org_edit"),
    path("admin/add-club", views.admin_add_club, name="admin_add_club"),
    path("portal/<int:org_id>", views.org_portal, name="org_portal"),
]
