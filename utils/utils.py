from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import decimal

from django.http import HttpRequest

from cobalt.settings import GLOBAL_CURRENCY_SYMBOL


def cobalt_paginator(
    request: HttpRequest,
    events_list: list,
    items_per_page: int = 30,
    page_no: int = None,
) -> Paginator.page:
    """common pagination function

    Args:
        page_no(int): optional page number to override what is in Request
        request(HTTPRequest): standard request object
        events_list(list): list of things to paginate
        items_per_page(int): number of items on a page

    Returns: list
    """

    page = page_no or request.GET.get("page", 1)
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


def cobalt_currency(number):
    """take a number and return it as a printable currency"""

    return f"{GLOBAL_CURRENCY_SYMBOL}{number:,.2f}".replace("$-", "-$")
