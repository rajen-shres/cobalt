from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required()
def covid_htmx(request):
    """return current state of users covid status as HTML"""

    return render(request, "accounts/profile/covid_htmx.html")


@login_required()
def covid_user_confirm_htmx(request):
    """Update users covid status"""

    request.user.covid_status = request.user.CovidStatus.USER_CONFIRMED
    request.user.save()
    return render(request, "accounts/profile/covid_htmx.html")


@login_required()
def covid_user_exempt_htmx(request):
    """Update users covid status to anti-vaxxer"""

    request.user.covid_status = request.user.CovidStatus.USER_EXEMPT
    request.user.save()
    return render(request, "accounts/profile/covid_htmx.html")
