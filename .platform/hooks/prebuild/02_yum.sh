#!/bin/bash

yum -y install amazon-efs-utils
yum -y install postgresql.x86_64
yum -y install git

# Install AWS CLI if not present. This is used to manage email suppression lists
if [ ! -f "/usr/local/bin/aws" ]; then
  echo "Installing AWS CLI V2"
  cd /tmp
  curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
  unzip -o awscliv2.zip
  ./aws/install
fi

