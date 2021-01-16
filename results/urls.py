from django.urls import path
from . import views

app_name = "results"  # pylint: disable=invalid-name

urlpatterns = [
    path("", views.home, name="results"),
]
