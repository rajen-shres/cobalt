:orphan:

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

==================================
Adding SMS to Cobalt
==================================

Pre-requisites
==============

First, set up your basic Cobalt environment on AWS (see :doc:`../tutorials/getting_started`
and :doc:`../tutorials/aws_overview`).

SNS Configuration
=================

Through the AWS Console grant access to SNS for the id you are using for Cobalt.

Environment Variables
=====================

Cobalt uses the same standard environment variables for SMS i.e.
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_REGION_NAME`.

If you have given permission correctly to this user account then there is no further
configuration needed on the Cobalt side.