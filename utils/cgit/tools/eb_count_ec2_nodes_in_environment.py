#!/usr/bin/env python

# Little script to count the number of EC2 instances in an environment.
# Called by the release to prod and UAT process to see if we need to add another
# instance to avoid 502 Gateway errors which happen if we upgrade with only one instance
import sys
import boto3
import os

try:
    environment = sys.argv[1]
except IndexError:
    print(f"\nUsage: {sys.argv[0]} environment_name\n")
    sys.exit(1)

ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

eb_client = boto3.client(
    "elasticbeanstalk",
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    region_name="ap-southeast-2",
)


print(
    eb_client.describe_environment_resources(EnvironmentName=environment)[
        "EnvironmentResources"
    ]["Instances"]
)

instances = len(
    eb_client.describe_environment_resources(EnvironmentName=environment)[
        "EnvironmentResources"
    ]["Instances"]
)

print(instances)
