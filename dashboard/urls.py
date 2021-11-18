from django.urls import path
from . import views

app_name = "dashboard"  # pylint: disable=invalid-name

urlpatterns = [
    #    path("", views.home, name="home"),
    path("", views.dashboard, name="dashboard"),
    path("experiment", views.experiment, name="experiment"),
    path("logged-out", views.logged_out, name="logged_out"),
    path("help", views.help, name="help"),
    path("scroll1", views.scroll1, name="scroll1"),
    path("scroll2", views.scroll2, name="scroll2"),
]
