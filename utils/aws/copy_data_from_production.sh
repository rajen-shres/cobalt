#!/bin/sh

unset AWS_SECRET_ACCESS_KEY
unset AWS_ACCESS_KEY_ID
ENV=cobalt-production-green

# Dump data
#eb ssh $ENV --command "-f sudo /var/app/current/utils/aws/copy_data_from_production_dump.sh"

# Get instance
INSTANCE=$(eb list --verbose | grep $ENV | tail -1 | awk '{print $3}' | tr -d "'[],")

echo $INSTANCE
# Get IP of instance

IP=$(aws ec2 describe-instances --instance-ids $INSTANCE | grep PublicIpAddress | awk '{print $2}' | tr -d '",')
echo $IP

# Copy data down
scp -i ~/.ssh/cobalt.pem ec2-user@$IP:/cobalt-media/db.json /tmp/db.json

# Delete dump file from server
#eb ssh $ENV --command "-f sudo rm /cobalt-media/db.json"

# Clean database and load
psql -f utils/aws/rebuild_test_data.sql
./manage.py migrate
./manage.py loaddata /tmp/db.json



