from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone

@login_required
def home(request):
    return render(request, 'calendar_app/home.html')
