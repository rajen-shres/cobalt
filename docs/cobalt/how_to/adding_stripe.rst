:orphan:

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

==================================
Adding Stripe to Cobalt
==================================

Pre-requisites
==============

First, set up your basic Cobalt environment (see :doc:`../tutorials/getting_started`).

Stripe Setup
===============

Create an account with Stripe, you will need to use a unique email address, but Stripe
allow you to have as many test accounts as you like. You can then create an API key
through Stripe's web site.

Environment Variable
====================

You need to set `STRIPE_SECRET_KEY` and `STRIPE_PUBLISHABLE_KEY` to the values that you set up
in the previous step.

Running
=======

To run this in a hosted environment, you need to set up the web callback address within Stripe.

To run this in development, you need to install the Stripe API and run::

    stripe login
    stripe listen --forward-to 127.0.0.1:8000/payments/stripe-webhook