#!/bin/sh

# set env
`cat /opt/elasticbeanstalk/deployment/env | awk '{print "export",$1}'`

# active virtualenv
. /var/app/venv/staging-LQM1lest/bin/activate

# change into app dir
cd /var/app/current

# Dump database
./manage.py dumpdata --exclude auth.permission --exclude contenttypes > /cobalt-media/db.json
