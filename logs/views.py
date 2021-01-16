from .models import Log
from django.shortcuts import render
from django.contrib.auth.decorators import user_passes_test
from django.core.mail import send_mail
from cobalt.settings import DEFAULT_FROM_EMAIL, SUPPORT_EMAIL
from utils.utils import cobalt_paginator


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
    logevent.message = message[:199]
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

    events_list = Log.objects.all().order_by("-event_date")

    things = cobalt_paginator(request, events_list, 30)

    return render(request, "logs/event_list.html", {"things": things})
