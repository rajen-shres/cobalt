#!/bin/sh
# Create the test/uat database. $1 is name of database

. utils/cgit/tools/eb_env_setup.sh

echo "create database $1 with owner postgres;" > /tmp/sql.txt

./manage.py dbshell < /tmp/sql.txt