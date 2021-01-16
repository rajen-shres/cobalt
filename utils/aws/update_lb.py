#!/bin/env python
import boto3
import json
import sys

if len(sys.argv) != 2:
    print("\nUsage %s eb_environment_name\n" % sys.argv[0])
    sys.exit(1)
eb_environment_name = sys.argv[1]


def format_json(response):
    print(json.dumps(response, sort_keys=True, indent=4))
    return json.dumps(response)


print("Environment: %s" % eb_environment_name)

eb = boto3.client("elasticbeanstalk")
response = eb.describe_environment_resources(EnvironmentName=eb_environment_name)
env_load_balancer_arn = response["EnvironmentResources"]["LoadBalancers"][0]["Name"]
print("Load Balancer ARN: %s" % env_load_balancer_arn)

elbv2 = boto3.client("elbv2")

response = elbv2.describe_listeners(LoadBalancerArn=env_load_balancer_arn)
format_json(response)

listeners = response["Listeners"]

print("Found %s listener(s)" % len(listeners))

target_group_arn = None
listener_arn = None

for listener in listeners:
    print("Listener ARN %s" % listener["ListenerArn"])
    print("          Protocol: %s" % listener["Protocol"])
    print("              Port: %s" % listener["Port"])
    default_actions = listener["DefaultActions"]
    print("   Default Actions")
    for default_action in default_actions:
        print("             Action: %s" % default_action["Type"])
        if "TargetGroupArn" in default_action:
            target_group_arn = default_action["TargetGroupArn"]
            listener_arn = listener["ListenerArn"]
            print(
                "             Target Group ARN: %s" % default_action["TargetGroupArn"]
            )

    rules = elbv2.describe_rules(ListenerArn=listener["ListenerArn"])
    format_json(rules)

# response = elbv2.describe_load_balancers()
#
# lbs = response['LoadBalancers']
#
# for lb in lbs:
#     print(lb['LoadBalancerArn'])
#     print(lb['LoadBalancerName'])
#     print(lb['Type'])

print("**********************************")
print("**********************************")
print("**********************************")

# # fmt:off
# response = elbv2.create_rule(
#     Actions=[
#         {
#             'TargetGroupArn': target_group_arn,
#             'Type': 'forward',
#         },
#     ],
#     Conditions=[
#         {
#             'Field': 'path-pattern',
#             "PathPatternConfig": {
#                 "Values": [
#                     "/health",
#                     "/health/"
#                 ]
#             },
#         },
#     ],
#     ListenerArn=listener_arn,
#     Priority=1,
# )
#
# print(response)
