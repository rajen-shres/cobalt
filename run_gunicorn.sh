#!/bin/sh

. /home/bitnami/django-env.sh
cd /opt/bitnami/projects/cobalt
. myenv/bin/activate
cd cobalt

gunicorn --access-logfile /tmp/gunicorn.error --error-logfile /tmp/gunicorn.access --workers 3 --bind unix:/opt/bitnami/projects/cobalt/cobalt/cobalt.sock cobalt.wsgi
