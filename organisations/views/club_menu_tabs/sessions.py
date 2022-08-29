from django.shortcuts import render

from organisations.decorators import check_club_menu_access


@check_club_menu_access()
def refresh_sessions_tab(request, club):
    """The sessions tab hangs after we upload a file. This refreshes the whole tab"""

    print("club", club)

    return render(request, "organisations/club_menu/sessions.html", {"club": club})
