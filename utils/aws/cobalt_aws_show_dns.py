#!/bin/env python
import boto3
import json
import sys

COBALT_ZONE = "myabf.com.au."

client = boto3.client("route53")

# Get all hosted zones
response = client.list_hosted_zones()
zones = response["HostedZones"]

# Get our zone
cobalt_zone_id = None
for zone in zones:

    if zone["Name"] == COBALT_ZONE:
        cobalt_zone_id = zone["Id"]

if not cobalt_zone_id:
    print("Zone not found: %s" % COBALT_ZONE)
    sys.exit(1)

# Get DNS
response = client.list_resource_record_sets(HostedZoneId=cobalt_zone_id)
record_sets = response["ResourceRecordSets"]
print("\nDNS Entries for %s\n" % COBALT_ZONE)
for record_set in record_sets:
    if record_set["Type"] == "CNAME":
        resource_records = record_set["ResourceRecords"]
        for resource_record in resource_records:
            print("%s ==> %s" % (record_set["Name"], resource_record["Value"]))
print("\n")
