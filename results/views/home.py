from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse

from accounts.models import TeamMate
from organisations.models import MemberMembershipType
from results.models import PlayerSummaryResult, ResultsFile
from utils.utils import cobalt_paginator


@login_required()
def home(request):
    """Show main page when user clicks on Results from the main side menu"""

    # your results
    your_results = recent_results_paginator_htmx(request, query_only=True)

    # team mate results
    teammate_results = teammates_results_paginator_htmx(request, query_only=True)

    # club results
    club_results = club_results_paginator_htmx(request, query_only=True)

    # Add hx_post for paginator controls
    hx_post_dict = {
        "yours": reverse("results:recent_results_paginator_htmx"),
        "teammate": reverse("results:teammates_results_paginator_htmx"),
        "club": reverse("results:club_results_paginator_htmx"),
    }

    return render(
        request,
        "results/home/home.html",
        {
            "your_results": your_results,
            "teammate_results": teammate_results,
            "club_results": club_results,
            "hx_post_dict": hx_post_dict,
        },
    )


@login_required()
def recent_results_paginator_htmx(request, query_only=False):
    """show pages for the recent results. Returns paginated query set or HttpResponse.

    Can be called by the main results page to build the initial list or by the htmx call to paginate

    """

    results = PlayerSummaryResult.objects.filter(
        player_system_number=request.user.system_number,
        results_file__status=ResultsFile.ResultsStatus.PUBLISHED,
    ).order_by("result_date")

    things = cobalt_paginator(request, results)

    if query_only:
        return things

    # Add hx_post for paginator controls
    hx_post = reverse("results:recent_results_paginator_htmx")

    return render(
        request,
        "results/home/recent_results_table_htmx.html",
        {"things": things, "hx_post": hx_post},
    )


@login_required()
def teammates_results_paginator_htmx(request, query_only=False):
    """show pages for the recent results. Returns paginated query set or HttpResponse.

    Can be called by the main results page to build the initial list or by the htmx call to paginate

    """

    # team mate results
    team_mates = TeamMate.objects.filter(user=request.user)
    system_numbers = team_mates.values_list("team_mate__system_number", flat=True)

    teammate_results_qs = PlayerSummaryResult.objects.filter(
        player_system_number__in=system_numbers,
        results_file__status=ResultsFile.ResultsStatus.PUBLISHED,
    ).order_by("result_date")

    # paginate it
    teammate_results = cobalt_paginator(request, teammate_results_qs)

    # Add player name
    for teammate_result in teammate_results:
        for team_mate in team_mates:
            if (
                team_mate.team_mate.system_number
                == teammate_result.player_system_number
            ):
                teammate_result.teammate = team_mate.team_mate

    if query_only:
        return teammate_results

    # Add hx_post for paginator controls
    hx_post = reverse("results:teammates_results_paginator_htmx")

    return render(
        request,
        "results/home/teammate_results_table_htmx.html",
        {"things": teammate_results, "hx_post": hx_post},
    )


@login_required()
def club_results_paginator_htmx(request, query_only=False):
    """show pages for the recent results. Returns paginated query set or HttpResponse.

    Can be called by the main results page to build the initial list or by the htmx call to paginate

    """

    # club results
    your_clubs = (
        MemberMembershipType.objects.active()
        .filter(system_number=request.user.system_number)
        .values_list("membership_type__organisation", flat=True)
    )

    club_results_qs = ResultsFile.objects.filter(
        organisation_id__in=your_clubs,
        status=ResultsFile.ResultsStatus.PUBLISHED,
    ).order_by("created_at")

    # paginate it
    club_results = cobalt_paginator(request, club_results_qs)

    # augment data - name and date are on the player_summary_records
    for club_result in club_results:
        first_player = PlayerSummaryResult.objects.filter(
            results_file=club_result
        ).first()
        club_result.event_name = first_player.event_name
        club_result.result_date = first_player.result_date

    if query_only:
        return club_results

    # Add hx_post for paginator controls
    hx_post = reverse("results:club_results_paginator_htmx")

    return render(
        request,
        "results/home/club_results_table_htmx.html",
        {"things": club_results, "hx_post": hx_post},
    )
