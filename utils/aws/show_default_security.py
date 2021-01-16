#!/usr/bin/env python
import subprocess
import json

################################################
# list what is in the default security group   #
################################################

DEFAULT_SG = "sg-e6b3fd98"


def sec_from_instance(inst):

    result = subprocess.run(
        ["aws", "ec2", "describe-instances", "--instance-ids", inst],
        stdout=subprocess.PIPE,
    )

    js = json.loads(result.stdout.decode("utf-8"))

    data = js["Reservations"][0]["Instances"][0]["SecurityGroups"][0]["GroupId"]
    return data


def eb_list():

    result = subprocess.run(["eb", "list", "-v"], stdout=subprocess.PIPE)

    data = result.stdout.decode("utf-8").split("\n")

    # this will break for multiple instances

    print("\n")

    for line in data[3:-1]:
        line = line.replace("*", "")
        parts = line.split(":")
        name = parts[0].strip()
        inst = parts[1].strip()
        inst = inst[2:-2]
        print(name, sec_from_instance(inst))


def default_sec_grp():

    result = subprocess.run(
        ["aws", "ec2", "describe-security-groups", "--group-ids", DEFAULT_SG],
        stdout=subprocess.PIPE,
    )

    js = json.loads(result.stdout.decode("utf-8"))
    data = js["SecurityGroups"][0]

    print("\n")
    print(data["Description"])

    IPPerms = data["IpPermissions"]

    for IPP in IPPerms:
        print(
            "\n%s from %s to %s" % (IPP["IpProtocol"], IPP["FromPort"], IPP["ToPort"])
        )
        UGPs = IPP["UserIdGroupPairs"]
        for UGP in UGPs:
            if "Description" in UGP:
                print("%s - %s" % (UGP["GroupId"], UGP["Description"]))
            else:
                print("%s -" % UGP["GroupId"])

    print("\n")

    print("Revoke:")
    print(
        "aws ec2 revoke-security-group-ingress --group-id sg-e6b3fd98 --protocol [protocol] --port [port] --source-group [sec_grp]"
    )
    print("Authorise:")
    print(
        "aws ec2 authorize-security-group-ingress --group-id sg-e6b3fd98 --protocol [protocol] --port [port] --source-group [sec_grp]"
    )


eb_list()
default_sec_grp()
