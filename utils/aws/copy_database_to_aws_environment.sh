#!/bin/bash
##############################################################################################
# Script to set up a production copy database on another AWS environment such as Test or UAT #
#
# Set up EC2 - https://techviewleo.com/install-postgresql-12-on-amazon-linux/
#
# yum -y update
# sudo  amazon-linux-extras | grep postgre
# sudo tee /etc/yum.repos.d/pgdg.repo<<EOF
  #[pgdg12]
  #name=PostgreSQL 12 for RHEL/CentOS 7 - x86_64
  #baseurl=https://download.postgresql.org/pub/repos/yum/12/redhat/rhel-7-x86_64
  #enabled=1
  #gpgcheck=0
  #EOF

# sudo yum makecache
# sudo yum install postgresql12
##############################################################################################

# Get prod password
echo -n Production Database Password:
read -s PGPASSWORD

# Hardcode the ones that are unlikely to change and aren't passwords
POSTGRES_DB="ebdb"
POSTGRES_USER="postgres"
REMOTE_HOSTNAME="cobalt-production.c97jawiow7ed.ap-southeast-2.rds.amazonaws.com"
UAT_HOSTNAME="cobalt-test.c97jawiow7ed.ap-southeast-2.rds.amazonaws.com"


# Dump file location
DUMP_FILE="/tmp/db.dump"

# Dump command
/usr/pgsql-12/bin/pg_dump --exclude-table-data "public.notifications_abstractemail" --exclude-table-data "public.post_office_*" -h $REMOTE_HOSTNAME -p 5432 -d $POSTGRES_DB -U $POSTGRES_USER -F c -b -v -f $DUMP_FILE

# Load the database
echo "Loading database, dropping old DB..."
cat << EOF > /tmp/drop_db_prod_copy
\c postgres
drop database IF EXISTS prod_load;
create database prod_load with owner postgres;
EOF

/usr/pgsql-12/bin/psql </tmp/drop_db_prod_copy

# Load the database
echo "Loading the data, this will take a while..."
/usr/pgsql-12/bin/pg_restore -h UAT_HOSTNAME -p 5432 -U $POSTGRES_USER -d prod_load --no-owner --no-privileges --role=cobalt -v $DUMP_FILE

# sanitise data
./manage.py sanitise_production_data_for_testing

# check it works
./manage.py count_users