from django.urls import path
from . import views

app_name = "logs"  # pylint: disable=invalid-name

urlpatterns = [
    path("", views.home, name="logs"),
]
