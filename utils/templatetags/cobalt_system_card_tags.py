import logging
import pprint
import random

from django import template
from django.template.loader import get_template
from django.utils.dateformat import DateFormat
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.contrib.humanize.templatetags.humanize import intcomma

from cobalt.settings import GLOBAL_CURRENCY_SYMBOL
from utils.templatetags.cobalt_tags import cobalt_bs4_field

logger = logging.getLogger("cobalt")
register = template.Library()


@register.filter(name="edit_or_show")
def edit_or_show(value, editable=False):
    """Either show the field as text, or show it as an editable field depending upon the flag editable"""

    if not value:
        return None

    if not editable:
        return value

    return cobalt_bs4_field(value, no_label=True)
