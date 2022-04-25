""" We needed to do some testing on the htmx search and it seemed useful to add a test url for it """
from django.shortcuts import render


def htmx_search(request):
    return render(request, "tests/search/htmx_search.html")
