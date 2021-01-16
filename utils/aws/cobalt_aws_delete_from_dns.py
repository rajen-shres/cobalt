#!/bin/env python
import boto3
import json
import sys

COBALT_ZONE = "myabf.com.au."
COBALT_ZONE_DNS = ".myabf.com.au"

if len(sys.argv) != 2:
    print("\nUsage %s dns_name\n" % sys.argv[0])
    sys.exit(1)

eb_dns_name = sys.argv[1]

route53 = boto3.client("route53")

# Get all hosted zones
response = route53.list_hosted_zones()
zones = response["HostedZones"]

# find our zone
cobalt_zone_id = None
for zone in zones:

    if zone["Name"] == COBALT_ZONE:
        cobalt_zone_id = zone["Id"]

if not cobalt_zone_id:
    print("Hosted Zone not found: %s" % COBALT_ZONE)
    sys.exit(1)

# Check DNS
already_in_dns = False
response = route53.list_resource_record_sets(HostedZoneId=cobalt_zone_id)
record_sets = response["ResourceRecordSets"]

for record_set in record_sets:
    if record_set["Type"] == "CNAME":
        if record_set["Name"] == f"{eb_dns_name}{COBALT_ZONE_DNS}.":
            already_in_dns = True

if not already_in_dns:
    print("\nEntry not present in DNS.\n")
    sys.exit(1)

# Get CNAME
response = route53.list_resource_record_sets(HostedZoneId=cobalt_zone_id)
record_sets = response["ResourceRecordSets"]

cname = None
for record_set in record_sets:
    if (
        record_set["Type"] == "CNAME"
        and record_set["Name"] == f"{eb_dns_name}{COBALT_ZONE_DNS}."
    ):
        cname = record_set["ResourceRecords"][0]["Value"]

if cname is None:
    print("\nError - couldn't find match\n")
    sys.exit(1)

# make change

response = route53.change_resource_record_sets(
    ChangeBatch={
        "Changes": [
            {
                "Action": "DELETE",
                "ResourceRecordSet": {
                    "Name": f"{eb_dns_name}{COBALT_ZONE_DNS}",
                    "ResourceRecords": [{"Value": cname}],
                    "TTL": 300,
                    "Type": "CNAME",
                },
            },
        ],
        "Comment": f"Deleted {eb_dns_name}",
    },
    HostedZoneId=cobalt_zone_id,
)

if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
    print(f"\nDeleted {eb_dns_name}{COBALT_ZONE_DNS} ==> {cname}\n")
    print("Command succesful\n")
else:
    print("\nAn error occurred.\n")
    print(response)
    print("\nAn error occurred.\n")
