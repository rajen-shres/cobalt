"""
WSGI config for cobalt project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/2.1/howto/deployment/wsgi/
"""
import newrelic.agent

newrelic.agent.initialize("/etc/newrelic-infra.yml")

import os  # noqa: 402

from django.core.wsgi import get_wsgi_application  # noqa: 402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cobalt.settings")

application = get_wsgi_application()
