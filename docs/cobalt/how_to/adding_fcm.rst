:orphan:

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

==================================
Adding FCM to Cobalt
==================================

We use Google's Firebase Cloud Messaging (FCM) to send notifications to the Mobile App.

Pre-requisites
==============

First, set up your basic Cobalt environment (see :doc:`../tutorials/getting_started`).

FCM Setup
=========

Create an account with Google and enable FCM. The Internet has a lot of resources to explain how to
do this.

Environment Variable
====================

You need to download a configuration file from FCM and have the variable
`GOOGLE_APPLICATION_CREDENTIALS` point to its location.