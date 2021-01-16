#!/bin/sh

FILE=/tmp/trigger.txt
if test -f "$FILE"; then

rm $FILE

/var/app/current/utils/aws/rebuild_test_database_postgres.sh

fi
