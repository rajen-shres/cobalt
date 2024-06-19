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

    # Note on type conversion:
    # Decimal(float(21.6)) = Decimal(21.60000000000000142108547152020037174224853515625)
    # so if this conversion is used 2.6 will be rounded to 2.61.
    # Decimal("21.6") = Decimal(21.6) which will round correctly
    # If the supplied number is already a Decimal, just use it.

    cent = decimal.Decimal("0.01")
    dec_input = (
        number if type(number) == type(cent) else decimal.Decimal(f"{number:.4f}")
    )

    result = float(dec_input.quantize(cent, rounding=decimal.ROUND_UP))

    # JPG Debug
    # print(f"*** cobalt_round *** {number} => {result}   Input: {type(number)}")

    return result

    # return float(
    #     decimal.Decimal(float(number)).quantize(cent, rounding=decimal.ROUND_UP)
    # )


def cobalt_currency(number):
    """take a number and return it as a printable currency"""

    return f"{GLOBAL_CURRENCY_SYMBOL}{number:,.2f}".replace("$-", "-$")
