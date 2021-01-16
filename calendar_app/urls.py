from django.urls import path
from . import views

app_name = "calendar"  # pylint: disable=invalid-name

urlpatterns = [
    path("", views.home, name="calendar"),
]
