import random

from django import template
from django.template.defaultfilters import striptags
from django.utils.dateformat import DateFormat
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.contrib.humanize.templatetags.humanize import intcomma
from widget_tweaks.templatetags.widget_tweaks import render_field, FieldAttributeNode

from cobalt.settings import GLOBAL_CURRENCY_SYMBOL

register = template.Library()


# custom filter for datetime so we can get "am" amd "pm" instead of "a.m." and "p.m."
# accepted datetime object or time object
# returns e.g. 10am, 7:15pm 10:01am
@register.filter(name="cobalt_time", expects_localtime=True)
def cobalt_time(value):
    if not value:
        return None

    hour_str = value.strftime("%I")
    min_str = value.strftime("%M")
    ampm_str = value.strftime("%p").replace(".", "").lower()
    hour_num = "%d" % int(hour_str)

    if min_str == "00":
        return f"{hour_num}{ampm_str}"
    else:
        return f"{hour_num}:{min_str}{ampm_str}"


# custom filter for datetime to format as full date
@register.filter(name="cobalt_nice_date", expects_localtime=True)
def cobalt_nice_date(value):
    if not value:
        return None

    return DateFormat(value).format("l jS M Y")


# custom filter for datetime to format as full date
@register.filter(name="cobalt_nice_datetime", expects_localtime=True)
def cobalt_nice_datetime(value):
    if not value:
        return None

    date_part = cobalt_nice_date(value)
    time_part = cobalt_time(value)

    return f"{date_part} {time_part}"


# custom filter for user which includes link to public profile
@register.filter(name="cobalt_user_link", is_safe=True)
def cobalt_user_link(user):
    if not user:
        return None

    url = reverse("accounts:public_profile", kwargs={"pk": user.id})
    return format_html("<a href='{}'>{}</a>", mark_safe(url), user)


# custom filter for user which includes link to public profile
# Short version - name only, no system number
@register.filter(name="cobalt_user_link_short", is_safe=True)
def cobalt_user_link_short(user):
    if not user:
        return None
    try:
        url = reverse("accounts:public_profile", kwargs={"pk": user.id})
        return format_html(
            "<a target='_blank' href='{}'>{}</a>", mark_safe(url), user.full_name
        )
    # Try to return the object if it was not a User
    except AttributeError:
        return user


# return formatted bridge credit number
@register.filter(name="cobalt_credits", is_safe=True)
def cobalt_credits(credits_amt):
    try:
        credits_amt = float(credits_amt)
    except ValueError:
        return None

    word = "credit" if credits_amt == 1.0 else "credits"

    try:
        if int(credits_amt) == credits_amt:
            credits_amt = int(credits_amt)
        ret = f"{credits_amt:,} {word}"
    except TypeError:
        ret = None

    return ret


# custom filter for email address which hides the address. Used by admin email viewer
@register.filter(name="cobalt_hide_email", is_safe=True)
def cobalt_hide_email(email):
    if not email:
        return None

    loc = email.find("@")
    last_fullstop = email.rfind(".")

    if loc and last_fullstop:
        hidden_email = "*" * len(email)
        hidden_email = hidden_email[:loc] + "@" + hidden_email[loc + 1 :]  # noqa: E203
        hidden_email = hidden_email[:last_fullstop] + email[last_fullstop:]
        return hidden_email
    else:
        return "*******************"


# return class of object - used by search
@register.filter(name="get_class")
def get_class(value):
    return value.__class__.__name__


# Return number formatted with commas and 2 decimals
@register.filter(name="cobalt_number", is_safe=True)
def cobalt_number(dollars):
    dollars = round(float(dollars), 2)
    return "%s%s" % (intcomma(int(dollars)), ("%0.2f" % dollars)[-3:])


# Return number formatted as currency
@register.filter(name="cobalt_currency", is_safe=True)
def cobalt_currency(dollars):
    dollars = round(float(dollars), 2)
    return "%s%s%s" % (
        GLOBAL_CURRENCY_SYMBOL,
        intcomma(int(dollars)),
        ("%0.2f" % dollars)[-3:],
    )


# Return random bootstrap colour - useful for card headers from lists
@register.simple_tag(name="cobalt_random_colour")
def cobalt_random_colour():
    colours = ["primary", "info", "warning", "danger", "success", "rose"]

    return random.choice(colours)


# return value from key for an array in a template. Django doesn't do this out of the box
@register.filter(name="cobalt_dict_key")
def cobalt_dict_key(my_dict, my_keyname):

    try:
        return my_dict[my_keyname]
    except (KeyError, TypeError):
        return ""


def _add_class(field):
    """sub function to add class to HTML string"""

    html = field.__str__()
    # class to add depends on type of field
    if field.widget_type == "checkbox":
        class_to_add = "form-check-input"
    else:
        class_to_add = "form-control"

    # Summernote is a special case
    if "summernote" in field.widget_type:
        loc = html.find("<textarea")
        return f'{html[:loc + 10]}class="{class_to_add}" {html[loc + 10:]}'

    # Add our bootstrap class to string
    # If there is a class tag already then use that
    loc = html.find("class=")
    if loc >= 0:
        return f"{html[:loc + 7]}{class_to_add} {html[loc + 7:]}"

    # no class tag insert before name
    loc = html.find("name=")
    if loc >= 0:
        return f'{html[:loc]}class="{class_to_add}" {html[loc:]}'

    # no name either, sort if we get a real example of this
    print("Error: cobalt_bs4_field cannot find class or name in object")
    return html


@register.simple_tag
def cobalt_bs4_field(field):
    """Format a field for a standard Bootstrap 4 form element.

    Returns a form-group div with the field rendered inside
    Will include a label if the type of field suits it.

    This is a general tag to be used for any field. It tries
    to work out how to format the HTML based upon the type of field.

    use it per field so you can format the elements individually.

    e.g.

    <div class="col-6">{% cobalt_bs4_field form.field1 %}</div>
    <div class="col-6">{% cobalt_bs4_field form.field2 %}</div>
    """

    # We are going to use the field to generate most things, we just wrap around it

    # Get string from field and add class
    html = _add_class(field)

    # handle checkboxes
    if field.widget_type == "checkbox":
        html = f"""
                <span class="cobalt-form-error">{striptags(field.errors)}</span>
                <div class="form-check">
                    <label class="form-check-label">
                    {html}
                  {field.label}
                  <span class="form-check-sign">
                    <span class="check"></span>
                  </span>
                </label>
                 </div>
                """

    else:

        # which widget types do not want a label
        no_label_types = ["summernoteinplace", "select"]

        # Add errors
        html = (
            f'<span class="cobalt-form-error">{striptags(field.errors)}</span>\n{html}'
        )

        # Add labels
        if field.label and field.widget_type not in no_label_types:
            html = f'<label class="bmd-label-floating" for="{field.id_for_label}">{field.label}</label>\n{html}'

        # Now wrap in form group
        html = f'<div class="form-group">\n{html}\n</div>'

    return mark_safe(html)
