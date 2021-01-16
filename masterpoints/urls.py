from django.urls import path
from . import views

app_name = "masterpoints"  # pylint: disable=invalid-name

urlpatterns = [
    path("", views.masterpoints_detail, name="masterpoints"),
    path("<int:years>/", views.masterpoints_detail, name="masterpoints_years"),
    path(
        "view/<int:system_number>/",
        views.masterpoints_detail,
        name="masterpoints_detail",
    ),
    path(
        "view/<int:system_number>/<int:years>/",
        views.masterpoints_detail,
        name="masterpoints_detail_years",
    ),
    path(
        "system_number_lookup", views.system_number_lookup, name="system_number_lookup"
    ),
    path("masterpoints_search", views.masterpoints_search, name="masterpoints_search"),
]
