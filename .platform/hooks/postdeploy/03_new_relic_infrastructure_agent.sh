#!/bin/bash

# It is recommended to run this from .ebextensions but that seems like the old way of doing it
# In addition we don't get access to the environment variables on a new install, so better to do it afterwards

echo "Setting up the New Relic Infrastructure Agent..."

# Create config file - put license key into it and override default hostname so we know what environment this is for
CONFIG_FILE=$(grep NEW_RELIC_CONFIG_FILE /opt/elasticbeanstalk/deployment/env | tr "=" " " | awk '{print $2}')
COBALT_HOSTNAME=$(grep COBALT_HOSTNAME /opt/elasticbeanstalk/deployment/env | tr "=" " " | awk '{print $2}')
LICENSE=$(grep license_key "$CONFIG_FILE" | awk '{print $3}')

echo "license_key: $LICENSE" > /etc/newrelic-infra.yml
LOCAL_NAME=$(hostname | tr "." " " | awk '{print$1}')
echo "\n\noverride_hostname: $LOCAL_NAME.$COBALT_HOSTNAME" > /etc/newrelic-infra.yml

chmod 644 /etc/newrelic-infra.yml

# Create the agent’s yum repository
curl -o /etc/yum.repos.d/newrelic-infra.repo https://download.newrelic.com/infrastructure_agent/linux/yum/amazonlinux/2/x86_64/newrelic-infra.repo
# Update your yum cache
yum -q makecache -y --disablerepo='*' --enablerepo='newrelic-infra'
# Run the installation script
yum install newrelic-infra -y

echo "Finished setting up the New Relic Infrastructure Agent."