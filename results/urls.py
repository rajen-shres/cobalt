from django.urls import path

import results.views.core
from results.views.core import home

app_name = "results"  # pylint: disable=invalid-name

urlpatterns = [
    path("", home, name="results"),
    path(
        "results-summary/<int:results_file_id>",
        results.views.core.usebio_mp_pairs_results_summary_view,
        name="results_usebio_mp_pairs_results_summary_view",
    ),
]
