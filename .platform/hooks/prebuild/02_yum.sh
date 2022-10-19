#!/bin/bash

yum -y install amazon-efs-utils
yum -y install postgresql.x86_64
yum -y install git

# Install AWS CLI if not present
if [ ! -f "/bin/aws" ]; then
  cd /tmp
  curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
  unzip -o awscliv2.zip
  ./aws/install
fi

