from django.urls import path
from results.views.core import home

app_name = "results"  # pylint: disable=invalid-name

urlpatterns = [
    path("", home, name="results"),
]
