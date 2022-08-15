from tests.views import htmx_search, button_test
from django.urls import path

app_name = "tests"

urlpatterns = [
    path("htmx-search", htmx_search, name="htmx_search"),
    path("button-test", button_test, name="button_text"),
]
