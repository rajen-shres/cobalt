#!/bin/sh
####################################################################
# Script to create an off-system backup of the production database #
# Just in case we ever have a problem with AWS                     #
#                                                                  #
# We need ~/Development/cobalt_prod_copy to be set up as a         #
# development environment with a virtual env called myenv in the   #
# root.                                                            #
# If you need to recreate this run:                                #
#   virtualenv myenv                                               #
#   mkdir cobalt                                                   #
#   . ./myenv/bin/activate                                         #
#   cd cobalt                                                      #
#   git init                                                       #
#   git remote add origin https://github.com/abftech/cobalt.git    #
#   eb init                                                        #
####################################################################

ENV=cobalt-production-green

# Load default environment settings
. ~/Dropbox/bin/cobalt_env.sh

# Override some vars
export RDS_DB_NAME=prod_load
unset AWS_SECRET_ACCESS_KEY
unset AWS_ACCESS_KEY_ID

# set up virtual env and get the prod version of the code
cd ~/Development/cobalt_prod_copy
. myenv/bin/activate
cd cobalt

# Get an instance
INSTANCE=$(eb list --verbose | grep $ENV | awk 'NF>1{print $NF}' | tr -d "'" | tr -d "]" | tr -d "[")
echo "Instance is $INSTANCE"

# Get IP of instance
IP=$(aws ec2 describe-instances --instance-ids $INSTANCE | grep PublicIpAddress | head -1 | awk '{print $2}' | tr -d '",')
echo "IP Address of $ENV is $IP"

# Get which application is installed on this environment
APP=$(eb status $ENV | grep Deploy | awk '{print $3}')

# Use aws cli to get the description for this application
DESC=$(aws elasticbeanstalk describe-application-versions --version-label "$APP" | grep Description | awk '{print $2}' | tr -d '"' | tr -d ,)

# Description is branch@timestamp - get branch
THISBRANCH=$(echo $DESC | tr '@' ' ' | awk '{print $1}')

# Make sure we have latest copy of branch
git fetch origin $THISBRANCH
git checkout $THISBRANCH

# Pip stuff
pip install -r requirements.txt

# Dump data
echo "sshing to $ENV to run dump command..."
eb ssh -n 1 $ENV --command "-f sudo /var/app/current/utils/aws/copy_data_from_production_dump.sh"

# The extract could still be running, so we look for the file to stop changing
echo "Checking for file export to be finished..."
file_age=0
while [ $file_age -lt 20 ]
do
   file_age=$(eb ssh -n 1 $ENV --command "echo \$((\$(date +%s) - \$(date +%s -r "/cobalt-media/db.json")))" 2>/dev/null | head -1)
   echo "File age: $file_age"
   sleep 5
done

# Passed
echo "File is old enough ($file_age seconds). Starting download..."

# Copy data down
echo "Downloading file..."
echo "scp -i ~/.ssh/cobalt.pem ec2-user@$IP:/cobalt-media/db.json ~/cobalt_backup/db.json"
scp -i ~/.ssh/cobalt.pem ec2-user@$IP:/cobalt-media/db.json ~/cobalt_backup/db.json

# Delete dump file from server
echo "sshing to $ENV to delete backup file..."
eb ssh -n 1 $ENV --command "-f sudo rm /cobalt-media/db.json"

# Check we can load the database
echo "Loading database, dropping old DB..."
cat << EOF > /tmp/drop_db_prod_copy
\c postgres
drop database IF EXISTS prod_load;
create database prod_load with owner cobalt;
EOF

psql </tmp/drop_db_prod_copy

# Run migrations and load the database
./manage.py migrate
echo "Loading the data, this will take a while..."
./manage.py loaddata ~/cobalt_backup/db.json

# check it works
# ./manage.py count_users

