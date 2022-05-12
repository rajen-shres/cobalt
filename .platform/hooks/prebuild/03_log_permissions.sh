#!/bin/bash

echo "Install setting permission on log file" >> /var/log/cobalt.log

chmod 777 /var/log/cobalt.log

# We want to be able to read the /var/log/messages file to see recent errors
# We run as webapp and the file is owned by root with 600 permissions
# We can't just change the permissions as the file gets rotated and the permissions
# get recreated, so we need to edit the syslog file. This is unlikely to cause a problem
# unless there is a major change to AWS Linux, but just in case we check that the file size
# is exactly what we expect it to be before we change it
FILE_SIZE=$(wc /etc/logrotate.d/syslog | awk '{print $3}')
if [ "$FILE_SIZE" -eq 224 ]; then
  sed -i '/sharedscripts/a create 0644' /etc/logrotate.d/syslog
fi

chmod 644 /etc/logrotate.d/syslog