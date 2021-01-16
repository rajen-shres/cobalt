from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
#from django.contrib.auth import User
from django.http import HttpResponse
from django.utils import timezone
#from .models import Match, Session, Section, Tournament, Event, mpMatch, mpMatchPair
#from general.models import Club, Pair
#from movements.models import Movement, MovementBoardRound

@login_required
def home(request):
    return render(request, 'results/home.html')

#@login_required
