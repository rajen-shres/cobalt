from datetime import timedelta

from django.contrib.auth.decorators import user_passes_test
from django.core.mail import send_mail
from django.shortcuts import render
from django.utils import timezone
from django.utils.html import strip_tags

from cobalt.settings import DEFAULT_FROM_EMAIL, SUPPORT_EMAIL
from utils.utils import cobalt_paginator
from .models import Log


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def log_event(user, severity, source, sub_source, message, request=None):
    if request:
        ip = get_client_ip(request)
    else:
        ip = None

    logevent = Log()
    logevent.user = user
    logevent.ip = ip
    logevent.severity = severity
    logevent.source = source[:30]
    logevent.sub_source = sub_source[:50]
    logevent.message = message
    logevent.save()

    if severity == "CRITICAL":
        mail_subject = "%s - %s" % (severity, source)
        message = "Severity: %s\nSource: %s\nSub-Source: %s\nUser: %s\nMessage: %s" % (
            severity,
            source,
            sub_source,
            user,
            message,
        )
        send_mail(
            mail_subject,
            message,
            DEFAULT_FROM_EMAIL,
            SUPPORT_EMAIL,
            fail_silently=False,
        )


@user_passes_test(lambda u: u.is_superuser)
def home(request):
    form_severity = request.GET.get("severity")
    form_source = request.GET.get("source")
    form_sub_source = request.GET.get("sub_source")
    form_days = request.GET.get("days")
    form_user = request.GET.get("user")

    days = int(form_days) if form_days else 7

    ref_date = timezone.now() - timedelta(days=days)

    events_list = Log.objects.filter(event_date__gte=ref_date)

    # only show sub sources if sources has been selected
    sub_sources = None

    if form_severity not in ["All", None]:
        events_list = events_list.filter(severity=form_severity)

    if form_user not in ["All", None]:
        events_list = events_list.filter(user__contains=form_user)

    if form_source not in ["All", None]:
        events_list = events_list.filter(source=form_source)
        sub_sources = events_list.values("sub_source").distinct()

        if form_sub_source not in ["All", None]:
            events_list = events_list.filter(sub_source=form_sub_source)

    # lists should be based upon other filters
    severities = events_list.values("severity").distinct()
    sources = events_list.values("source").distinct()
    users = events_list.exclude(user=None).values("user").distinct()

    unique_users = []
    for user in users:
        this_user = strip_tags(user["user"])
        if this_user not in unique_users:
            unique_users.append(this_user)

    unique_users.sort()

    return render(
        request,
        "logs/event_list.html",
        {
            "things": events_list,
            "severities": severities,
            "days": days,
            "form_severity": form_severity,
            "sources": sources,
            "form_source": form_source,
            "form_sub_source": form_sub_source,
            "sub_sources": sub_sources,
            "form_user": form_user,
            "users": unique_users,
        },
    )
