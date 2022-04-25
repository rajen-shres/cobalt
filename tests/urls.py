from tests.views import htmx_search
from django.urls import path

app_name = "tests"

urlpatterns = [
    path("htmx-search", htmx_search, name="htmx_search"),
]
