#!/bin/sh

# Get session id (random string)
SESSIONID=$1

# set env
`cat /opt/elasticbeanstalk/deployment/env | awk '{print "export",$1}'`

# active virtualenv
. /var/app/venv/staging-LQM1lest/bin/activate

# change into app dir
cd /var/app/current

# Dump database, with exclusions
./manage.py dumpdata --natural-foreign --natural-primary --exclude post_office.Email  --exclude notifications.Snooper --exclude auth.permission --exclude contenttypes --indent 4 -o /cobalt-media/$SESSIONID.json.gz