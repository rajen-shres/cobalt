from django.urls import path
from . import views

app_name = "xero"

urlpatterns = [
    path("callback", views.callback, name="xero_callback"),
    path("initialise", views.initialise, name="xero_initialise"),
    path("", views.home, name="xero_home"),
    path("config", views.home_configuration_htmx, name="xero_home_config_htmx"),
    path("refresh", views.refresh_keys_htmx, name="xero_refresh_keys_htmx"),
    path("run-xero-api", views.run_xero_api_htmx, name="run_xero_api_htmx"),
]
