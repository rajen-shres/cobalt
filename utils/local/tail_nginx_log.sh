#!/bin/sh

# Used by the log viewer to tail the nginx access log to show recent activity

log_file="/var/log/nginx/access.log"

# For development use a local file
if [ ! -f $log_file ]; then
  log_file="/Users/upstud/access.log"
fi

# Filter out Elasticbeanstalk health checks and calls with util in them (this screen)
tail -200 $log_file|grep -Ev "ELB-HealthChecker/2.0|utils" | tail -30