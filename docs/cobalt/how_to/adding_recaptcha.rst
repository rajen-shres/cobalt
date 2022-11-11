:orphan:

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

========================================
Adding Google Recaptcha to Cobalt
========================================

We use Google's Recaptcha2 to verify people who use the logged out contact form.

Pre-requisites
==============

First, set up your basic Cobalt environment (see :doc:`../tutorials/getting_started`).

Recaptcha Setup
===============

Create an account with Google and set up Recaptcha. The Internet has a lot of resources
to explain how to
do this.

Environment Variable
====================

You need to set `RECAPTCHA_SITE_KEY` and `RECAPTCHA_SECRET_KEY` to the values that you set up
in the previous step.