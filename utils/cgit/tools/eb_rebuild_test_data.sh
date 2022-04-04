#!/bin/sh
# Drop the test/uat database. $1 is name of database

. /var/app/current/utils/cgit/tools/eb_env_setup.sh

# Double check we are on an environment we expect to be on
if [ "$COBALT_HOSTNAME" = "test.myabf.com.au" ] || [ "$COBALT_HOSTNAME" = "uat.myabf.com.au" ]
then

utils/aws/rebuild_test_database_subcommands.sh

else
  echo "$COBALT_HOSTNAME not on list of expected hosts. Aborting."
fi