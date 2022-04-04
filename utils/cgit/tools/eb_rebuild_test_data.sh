#!/bin/sh
# Drop the test/uat database. $1 is name of database

. /var/app/current/utils/cgit/tools/eb_env_setup.sh

utils/aws/rebuild_test_database_subcommands.sh