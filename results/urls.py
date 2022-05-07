from django.urls import path

import results.views.core
import results.views.par_contract
import results.views.results_views
from results.views.core import home

app_name = "results"  # pylint: disable=invalid-name

urlpatterns = [
    path("", home, name="results"),
    path(
        "mp-pairs-results-summary/<int:results_file_id>",
        results.views.results_views.usebio_mp_pairs_results_summary_view,
        name="usebio_mp_pairs_results_summary_view",
    ),
    path(
        "mp-pairs-results-pair-details/<int:results_file_id>/<str:pair_id>",
        results.views.results_views.usebio_mp_pairs_details_view,
        name="usebio_mp_pairs_details_view",
    ),
    path(
        "mp-pairs-results-board-details/<int:results_file_id>/<int:board_number>/<str:pair_id>",
        results.views.results_views.usebio_mp_pairs_board_view,
        name="usebio_mp_pairs_board_view",
    ),
    path(
        "temp",
        results.views.par_contract.temp,
        name="usebio_mp_pairs_board_viewcssafsf",
    ),
]
