from django.shortcuts import render

from .decorators import user_is_club_director


@user_is_club_director()
def new_session(request, club):

    return render(request, "club_sessions/session.html")