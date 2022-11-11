:orphan:

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

.. image:: ../../images/aws.png
 :width: 300
 :alt: Amazon Web Services

=================
Deploying on AWS
=================

Amazon Web Services (AWS) is not required to use Cobalt, but the ABF version runs on AWS and
this document describes how to set Cobalt up on AWS if you want to.

Pre-requisites
==============

You will need an AWS account and credentials for an API Account.

You will need the Cobalt code installed and the AWS CLI and Elastic Beanstalk CLI.

As part of installing the AWS CLI you will set up the credentials, if for some reason
you haven't, or you wish to use different credentials, then you can set them as
environment variables.

Step 1 - Create a Security Group
================================

If you don't have a security group, then Elastic Beanstalk will create one for you. However,
if you have more than one environment (e.g. Production, Test and UAT), then if you try to remove
an environment it will attempt to delete the security group and will fail (after about 30 minutes
of trying).

Follow AWS instructions to create a security group.

Step 2 - Create a Database on RDS
=================================

Use the AWS web site to create a Database.

Step 3 - Set Up a Zone in Route 53
==================================

Use the AWS web site to create a DNS Zone in Route 53.

Step 4 - Create the Elastic Beanstalk Environment
=================================================

Build the environment by running::

    utils/aws/cobalt_aws_create_environment.py
