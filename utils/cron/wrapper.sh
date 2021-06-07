#!/bin/bash
# Wrapper for manage.py commands from cron fro AWS Elastic Beanstalk

# Activate virtual env
. /var/app/venv/staging-LQM1lest/bin/activate

# Change into project directory
cd /var/app/current/

# Source environment variables
`cat /opt/elasticbeanstalk/deployment/env | awk '{print "export",$1}'`

# Quotes are a problem so explicitly do something for those
tmpfile=$(mktemp /tmp/env.XXXXXX)
cat /opt/elasticbeanstalk/deployment/env | grep "'" | sed 's/.*/export &/' > $tmpfile
. $tmpfile

# run manage.py command
./manage.py $@