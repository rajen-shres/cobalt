"""
WSGI config for cobalt project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/2.1/howto/deployment/wsgi/
"""
import os
import newrelic.agent

NEWRELIC_INI = "/cobalt-media/admin/__confdata_/newrelic.ini"
if os.path.exists(NEWRELIC_INI):
    newrelic.agent.initialize("/cobalt-media/admin/__confdata_/newrelic.ini")

from django.core.wsgi import get_wsgi_application  # noqa: 402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cobalt.settings")

application = get_wsgi_application()
