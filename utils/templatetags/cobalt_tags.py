from django import template
from django.utils.dateformat import DateFormat
from django.urls import reverse
from django.utils.safestring import mark_safe

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
        time_str = f"{hour_num}{ampm_str}"
    else:
        time_str = f"{hour_num}:{min_str}{ampm_str}"

    return time_str


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
    return mark_safe(f"<a href='{url}'>{user}</a>")


# custom filter for user which includes link to public profile
# Short version - name only, no system number
@register.filter(name="cobalt_user_link_short", is_safe=True)
def cobalt_user_link_short(user):

    if not user:
        return None

    url = reverse("accounts:public_profile", kwargs={"pk": user.id})
    return mark_safe(f"<a href='{url}'>{user.full_name}</a>")


# return formatted bridge credit number
@register.filter(name="cobalt_credits", is_safe=True)
def cobalt_credits(credits):

    try:
        credits = float(credits)
    except ValueError:
        return mark_safe(None)

    if credits == 1.0:
        word = "credit"
    else:
        word = "credits"

    try:
        if int(credits) == credits:
            credits = int(credits)
        ret = f"{credits:,} {word}"
    except TypeError:
        ret = None

    return mark_safe(ret)

# custom filter for email address which hides the address. Used by admin email viewer
@register.filter(name="cobalt_hide_email", is_safe=True)
def cobalt_hide_email(email):

    if not email:
        return None

    loc = email.find("@")
    last_fullstop = email.rfind(".")

    if loc and last_fullstop:
        hidden_email = "*" * len(email)
        hidden_email = hidden_email[:loc] + "@" + hidden_email[loc+1:]
        hidden_email = hidden_email[:last_fullstop] + email[last_fullstop:]
        return mark_safe(hidden_email)
    else:
        return "*******************"

# return class of object - used by search
@register.filter(name="get_class")
def get_class(value):
    return value.__class__.__name__
