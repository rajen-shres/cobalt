from datetime import datetime
from decimal import Decimal

from django import template
from django.utils import timezone
from django.utils.safestring import mark_safe

from accounts.models import User
from utils.templatetags.cobalt_tags import (
    cobalt_currency,
    cobalt_nice_date_short,
    cobalt_nice_datetime_short,
)

register = template.Library()


@register.simple_tag
def cobalt_simple_table_header_tag(headers, align, heading_colour=None):
    """part of the cobalt_simple_table.html utility

    Generates the headers for a table

    """

    # Fields is a list from the template, but we want a list
    headers = headers.split()
    align = align.split()

    ret = "<tr>"

    for ind, header in enumerate(headers):

        # remove _
        header = header.replace("_", " ")

        # Handle colours
        colour = f" text-{heading_colour}" if heading_colour else ""
        ret += f"<th style='cursor: default' class='text-{align[ind]}{colour}'>{header}</th>"

    ret += "</tr>"

    return mark_safe(ret)


@register.simple_tag
def cobalt_simple_table_row_tag(row, fields, align):
    """part of the cobalt_simple_table.html utility

    takes in an indexed row such as a single row from iteration over a queryset and returns it as a table.

    """

    # Fields is a string from the template, but we want a list
    fields = fields.split()
    align = align.split()

    ret = "<tr>"

    for ind, field in enumerate(fields):

        val = getattr(row, field)
        extra_class = ""

        if isinstance(val, Decimal):
            val = cobalt_currency(val)

        elif isinstance(val, datetime):
            val = cobalt_nice_datetime_short(val)
            extra_class = " cobalt-no-wrap"

        elif isinstance(val, User):
            val = val.full_name
            extra_class = " cobalt-no-wrap"

        ret += f"<td style='cursor: default' class='text-{align[ind]} {extra_class}'>{val}</td>"

    ret += "</tr>"

    return mark_safe(ret)
