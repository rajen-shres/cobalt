from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import decimal


def cobalt_paginator(request, events_list, items_per_page=30, page_no=None):
    """common pagination function

    Args:
        request(HTTPRequest): standard request object
        events_list(list): list of things to paginate
        items_per_page(int): number of items on a page

    Returns: list
    """

    if page_no:
        page = page_no
    else:
        page = request.GET.get("page", 1)

    paginator = Paginator(events_list, items_per_page)
    try:
        events = paginator.page(page)
    except PageNotAnInteger:
        events = paginator.page(1)
    except EmptyPage:
        events = paginator.page(paginator.num_pages)

    return events


def cobalt_round(number):
    """round up to 2 decimal places

    Args:
        number(Float): number to round

    Returns: Float
    """

    cent = decimal.Decimal("0.01")

    return float(
        decimal.Decimal(float(number)).quantize(cent, rounding=decimal.ROUND_UP)
    )
