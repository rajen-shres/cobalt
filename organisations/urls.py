# pylint: disable=missing-module-docstring,missing-class-docstring
from django.urls import path
from . import views

app_name = "organisations"  # pylint: disable=invalid-name

urlpatterns = [
    path("org-search-ajax", views.org_search_ajax, name="org_search_ajax"),
    path("org-detail-ajax", views.org_detail_ajax, name="org_detail_ajax"),
    path("edit/<int:org_id>", views.org_edit, name="org_edit"),
]
