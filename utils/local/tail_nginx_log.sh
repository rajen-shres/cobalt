#!/bin/sh

# Used by the log viewer to tail the nginx access log to show recent activity

log_file="/var/log/nginx/access.log"

# For development use a local file
if [ ! -f $log_file ]; then
  log_file="/Users/upstud/access.log"
fi
tail -100 $log_file|grep -v ELB-HealthChecker/2.0 | tail -30