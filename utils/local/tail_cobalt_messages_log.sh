#!/bin/sh

# Used by the log viewer to tail the cobalt messages file

log_file="/var/log/cobalt.log"

# For development use a local file
if [ ! -f $log_file ]; then
  log_file="/Users/guthrie/cobalt.log"
fi

tail -30 $log_file