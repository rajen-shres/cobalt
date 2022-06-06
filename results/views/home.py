from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse

from results.models import PlayerSummaryResult, ResultsFile
from utils.utils import cobalt_paginator


@login_required()
def home(request):
    """Show main page when user clicks on Results from the main side menu"""

    results = PlayerSummaryResult.objects.filter(
        player_system_number=request.user.system_number,
        results_file__status=ResultsFile.ResultsStatus.PUBLISHED,
    ).order_by("result_date")

    # paginate it
    things = cobalt_paginator(request, results)

    # Add hx_post for paginator controls
    hx_post = reverse("results:recent_results_paginator")

    return render(
        request, "results/home/home.html", {"things": things, "hx_post": hx_post}
    )


@login_required()
def recent_results_paginator_htmx(request):
    """show pages for the recent results"""

    results = PlayerSummaryResult.objects.filter(
        player_system_number=request.user.system_number,
        results_file__status=ResultsFile.ResultsStatus.PUBLISHED,
    ).order_by("result_date")

    things = cobalt_paginator(request, results)

    # Add hx_post for paginator controls
    hx_post = reverse("results:recent_results_paginator")

    return render(
        request,
        "results/home/recent_results_table_htmx.html",
        {"things": things, "hx_post": hx_post},
    )
