from re import finditer

from django import template
from django.template.loader import get_template
from django.utils.safestring import mark_safe

from utils.templatetags.cobalt_tags import cobalt_bs4_field

register = template.Library()

# placeholder is where we put the number if we have one
PLACEHOLDER = "--NUMBER--"

card_mappings = {
    "C": f"<span class='club'>{PLACEHOLDER}</span>",
    "D": f"<span class='diamond'>{PLACEHOLDER}</span>",
    "H": f"<span class='heart'>{PLACEHOLDER}</span>",
    "S": f"<span class='spade'>{PLACEHOLDER}</span>",
    "N": f"<span class='nt'>{PLACEHOLDER}</span>",
}


def _card_symbol_change_sub(work_string, change_to, matches):
    """
    Args:
        work_string: The string provided
        change_to: what to replace with
        matches: a regex

    Returns:
        str

    """

    if not matches:
        return work_string

    # reverse the matches, so we can go through the string backwards, otherwise it will move as we edit it
    reverse_matches = []
    for match in matches:
        start_location = match.span()[0]
        end_location = match.span()[1]
        number_found = match.group()[0][0]

        # number found will actually be "!" if we don't get a number so change it
        if number_found == "!":
            number_found = ""

        reverse_matches.append(
            {
                "start_location": start_location,
                "end_location": end_location,
                "number_found": number_found,
            }
        )

    # now reverse it
    reverse_matches.reverse()

    # Go through and do the replacements
    for match in reverse_matches:
        work_string = f"""
        {work_string[:match["start_location"]]}
        {change_to}
        {work_string[match["end_location"]:]}"""

        # Put in replacement text
        work_string = work_string.replace(PLACEHOLDER, match["number_found"])

    return work_string


def _card_symbol_change(work_string, look_for, change_to=""):
    """look for a signature in the string and convert it

    Sometimes we have card symbols with numbers and sometimes without. We put the number inside the
    span, so:

    <span class="club">7</span>

    so we need to handle getting a string with, and without a number a little differently

    """

    # Work on it with the number
    matches = finditer(r"(\d)" + look_for, work_string)
    work_string = _card_symbol_change_sub(work_string, change_to, matches)

    # Same again without the number - above regex won't match of there is no number
    matches = finditer(look_for, work_string)
    work_string = _card_symbol_change_sub(work_string, change_to, matches)

    return work_string


def _card_symbol(value, qualifier=""):
    """common part of the card symbol calls"""

    for card_mapping in card_mappings:
        value = _card_symbol_change(
            value, f"{qualifier}{card_mapping}", card_mappings[card_mapping]
        )

    return mark_safe(value)


@register.filter(name="card_symbol_all")
def card_symbol_all(value):
    """Converts any C, D, H, S, N to a card symbol

    Use this for a string like "3C"
    use card_symbol_bang for strings like "I once bid 3!C and they bid 4!D"

    Also takes any connect number and formats that too

    """

    # Handle the special case of getting LINK- We need this because links can't start with a number
    value = value.replace("LINK-", "")

    return _card_symbol(value)


@register.filter(name="card_symbol_bang")
def card_symbol_bang(value):
    """Converts any !C, !D, !H, !S, !N to a card symbol

    use this for strings like "I once bid 3!C and they bid 4!D"
    Use card_symbol_all for a string like "3C"

    """

    return _card_symbol(value, r"\!")


@register.simple_tag(name="cobalt_edit_or_show")
def cobalt_edit_or_show(field, editable=False, display_name=False, min_width=False):
    """
    Either show the field as text, or show it as an editable field depending upon the flag editable

    This just saves having a million if statements in the system card templates

    Parameters:
        field: form value
        editable(bool): If True we show a form field, otherwise we show the text from the form value
        display_name(bool): Can't remember - LATER
        min_width(bool): Changes the class, so it's not expanded to full width

    """

    if not field:
        return "<h2>Programming Error. Expected form field.</h2>"

    if not editable:
        if not display_name:
            return card_symbol_bang(field.value())
        else:
            return "Fish - Later"

    field_template = get_template("accounts/system_card/template_tag_field.html")

    return field_template.render({"field": field, "min_width": min_width})
