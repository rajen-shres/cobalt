#!/bin/sh
# This is only used for one-off test systems e.g. Lightsail.

. /home/bitnami/django-env.sh
cd /opt/bitnami/projects/cobalt
. myenv/bin/activate
cd cobalt

# web: newrelic-admin run-program gunicorn --bind :8000 --workers 3 --threads 2 cobalt.wsgi:application
gunicorn --access-logfile /tmp/gunicorn.error --error-logfile /tmp/gunicorn.access --workers 3 --bind unix:/opt/bitnami/projects/cobalt/cobalt/cobalt.sock cobalt.wsgi
