#!/bin/sh
# Drop the test/uat database. $1 is name of database

. /var/app/current/utils/cgit/tools/eb_env_setup.sh

# Double check we are on an environment we expect to be on
if [ "$COBALT_HOSTNAME" = "test.myabf.com.au" ] || [ "$COBALT_HOSTNAME" = "uat.myabf.com.au" ]
then

  echo "drop database $1;" > /tmp/sql.txt
  ./manage.py dbshell < /tmp/sql.txt

else
  echo "$COBALT_HOSTNAME not on list of expected hosts. Aborting."
fi