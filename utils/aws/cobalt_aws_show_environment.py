#!/bin/env python
import boto3
import json
import sys

if len(sys.argv) != 2:
    print("\nUsage %s eb_environment_name\n" % sys.argv[0])
    sys.exit(1)

eb_environment_name = sys.argv[1]

ebclient = boto3.client("elasticbeanstalk")

response = ebclient.describe_environments(EnvironmentNames=[eb_environment_name])

if len(response["Environments"]) > 0:
    print("Environment exists")
else:
    print("Environment not found")

print(response)

print(json.dumps(response, sort_keys=True, indent=4))
