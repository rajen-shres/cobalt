.. _forums-overview:


.. image:: images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

Development Overview
====================

Cobalt is written in Django. It is assumed that you already know Python,
Django and the associated tools such as pip and virtualenv. If you don't
there are lots of resources available to help you.

Before you get started make sure you have the following installed:

- Python 3.7+
- pip
- virtualenv
- git
- postgresql (*optional but highly recommended*)

Development Environment Set Up
==============================

Code
----

You can use any OS you like for development, but for simplicity the commands
shown here are for a Unix style environment such as Linux or Mac OS. The
Windows equivalent commands will work just as well.

Here are the basic steps to get started::

    $ mkdir cobalt-project
    $ virtualenv myenv   # specify -P python3.7 or similar if that is not your default
    $ . virtualenv/bin/activate
    $ mkdir cobalt
    $ cd cobalt

Get code from github and set up::

    $ git init
    $ git remote add origin https://github.com/mguthrieabf/cobalt.git
    $ git pull origin master

Install requirements::

    $ pip install -r requirements.txt

Install development-only requirements::

    $ pip install -r requirements-dev.txt

We recommend using two pre-commits for Git which are described below. For now,
just install them using::

    $ pre-commit install

Database
--------

There are a number of problems with using SQLite3 especially on a Mac. It is
strongly recommended that even for development, you set up a local Postgresql
database.

Environment Variables
---------------------

.. highlight:: none

Before running manage.py you will need to set some environment variables::

    # Postgres - use your own settings
    export RDS_DB_NAME=ebdb
    export RDS_HOSTNAME=127.0.0.1
    export RDS_PORT=5432
    export RDS_USERNAME=cobalt
    export RDS_PASSWORD=password

    # Masterpoints server - not essential
    export GLOBAL_MPSERVER=http://localhost:8081

    # Email
    export EMAIL_HOST=smtp.something.com
    export EMAIL_HOST_USER=userid
    export EMAIL_HOST_PASSWORD=password
    export DEFAULT_FROM_EMAIL=donotreply@something.com

    # Stripe - for payments. Set up a free Stripe account
    export STRIPE_SECRET_KEY=sk_test_key
    export STRIPE_PUBLISHABLE_KEY=pk_test_key

    # AWS - for SMS
    export AWS_ACCESS_KEY_ID=SOMETHING
    export AWS_SECRET_ACCESS_KEY=KEY

.. highlight:: default

Management Commands
-------------------

In your development environment you will need to run some management
commands to set up static data. In the ABF system these get run automatically
as part of the deployment to AWS. The easiest way to identify what needs to be
run is to look at the commands that are run in AWS. Look in the root project
directly at .ebextensions/python.config.

Coding Standards
================

We try to follow basic Python and Django standards. To help to enforce this
the pre-commits for Git that you added earlier will run two things:

- **Black** - an opinionated code formatter. Black will reformat your code
  in a standard way. (It is called Black after the Henry Ford quote "Any colour
  as long as it is black"). Black can save you a lot of time as it allows you
  to write code in a way that is natural for writing (long lines, random choice of
  which quotes to use, etc) but then it will format it in a way that easier to read.

- **Flake8** - a code checker. Flake8 is a reasonably generous code checker. It
  provides a basic level of assurance that the code is formatted okay.

Additionally it is recommended the pylint is used before code is committed. Pylint
is far stricter than Flake8 so insisting that code is fully compliant with pylint
before allowing it to be committed would be too much. However, pylint will find a
lot of things that Flake8 won't. Run pylint but take its findings as recommendations
not hard requirements.

Documentation
=============

If you found this then you presumably know where the documentation lives. If not,
look at https://cobalt-bridge.readthedocs.io.

To update the documentation look in the cobalt sub-directory docs.
