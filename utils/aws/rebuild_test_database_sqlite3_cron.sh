#!/bin/sh

FILE=/tmp/trigger.txt
if test -f "$FILE"; then

rm $FILE

/var/app/current/aws/rebuild_test_database_sqlite3.sh

fi
