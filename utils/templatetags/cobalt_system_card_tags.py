from django import template
from utils.templatetags.cobalt_tags import cobalt_bs4_field

register = template.Library()


@register.simple_tag(name="cobalt_edit_or_show")
def cobalt_edit_or_show(value, editable=False, display_name=False):
    """Either show the field as text, or show it as an editable field depending upon the flag editable"""

    if not value:
        return None

    if not editable:
        if not display_name:
            return value.value()
        else:
            return "Fish"

    return value
