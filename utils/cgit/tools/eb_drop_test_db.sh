#!/bin/sh
# Drop the test/uat database. $1 is name of database

. /var/app/current/utils/cgit/tools/eb_env_setup.sh

echo "drop database $1;" > /tmp/sql.txt

./manage.py dbshell < /tmp/sql.txt