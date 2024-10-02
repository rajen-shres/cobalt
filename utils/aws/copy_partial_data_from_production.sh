#!/bin/sh
####################################################################
# Script load a partial dump of production into a dev environment  #
# Excludes teh Snooper and Email tables for practicality           #
# This is not suitable for offsite backup purposes                 #
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

# Generate a random string to act as a 'password'
# The file will be publicly readable so obscure it
SESSIONID=$(openssl rand -hex 12)
DUMPFILE="$SESSIONID.json.gz"

# Load default environment settings
. ~/Development/cobalt_prod_copy/myenv/cobalt_env.sh

# Override some vars
export RDS_DB_NAME=prod_load
# unset AWS_SECRET_ACCESS_KEY
# unset AWS_ACCESS_KEY_ID

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
git fetch origin $THISBRANCH:$THISBRANCH
git checkout $THISBRANCH

# Pip stuff
pip install -r requirements.txt

# Dump data
echo "sshing to $ENV to run dump command..."
eb ssh -n 1 $ENV --command "sudo /var/app/current/utils/aws/copy_partial_data_from_production_dump.sh $SESSIONID"

# Copy data down
echo "Downloading file..."
echo "scp -i ~/.ssh/cobalt.pem ec2-user@$IP:/cobalt-media/$DUMPFILE ~/cobalt_backup/$DUMPFILE"
scp -i ~/.ssh/cobalt.pem ec2-user@$IP:/cobalt-media/$DUMPFILE ~/cobalt_backup/$DUMPFILE

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
./manage.py loaddata ~/cobalt_backup/$SESSIONID.json
# ./manage.py loaddata  --exclude post_office --exclude notifications ~/cobalt_backup/$SESSIONID.json
