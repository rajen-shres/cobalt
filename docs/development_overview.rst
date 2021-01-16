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

Overview
--------

There are a few steps to follow:

- Set up development tools
- Set up database
- Set environment variables
- Set up static data

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
    $ git remote add origin https://github.com/abftech/cobalt.git
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

You will need to create a user. Start psql::

    postgres=# create user cobalt with encrypted password 'password';

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

    # Email - you can use the email server settings from AWS if you want
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

It is easiest to put this in a batch file, or even run it automatically when
you start your shell.

.. highlight:: default

Management Commands
-------------------

In your development environment you will need to run some management
commands to set up static data. In the ABF system these get run automatically
as part of the deployment to AWS. The easiest way to identify what needs to be
run is to look at the commands that are run in AWS. Look in the root project
directly at .platform/hooks/postdeploy/02_django.sh.

You might want to run these manually the first time and then automate it.

Test Data
---------

There are Django management commands within Cobalt that create test data.
They run from spreadsheets which you can obtain from the project team.

Combining it all
----------------

As a developer you will find yourself rebuilding the database quite often.
You can use a script to automate this for you.

For example::

    #!/bin/sh

    # copy test data from dropbox
    mkdir /tmp/test-data
    cp ~/Dropbox/Technology/Testing/test_data/upload/* /tmp/test-data

    # reset database
    psql -f ~/Dropbox/bin/rebuild_dev_db.sql

    # migrate
    ./manage.py migrate

    # static data
    ./manage.py createsu
    ./manage.py create_abf
    ./manage.py add_rbac_static_forums
    ./manage.py add_rbac_static_payments
    ./manage.py add_rbac_static_orgs
    ./manage.py add_rbac_static_events
    ./manage.py add_rbac_static_notifications
    ./manage.py create_states

    # Test data
    ./manage.py add_test_data
    #./manage.py createdummyusers
    #./manage.py importclubs

rebuild_dev_db.sql::

    \c postgres
    drop database ebdb;
    create database ebdb with owner cobalt;

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

Github Branching
================

The documentation for this is in Confluence.

https://abftech.atlassian.net/wiki/spaces/COBALT/pages/6586408/Git+Process+for+Working+on+Jira+Tasks

There are also some support tools to assist with this.

https://abftech.atlassian.net/wiki/spaces/COBALT/pages/576651366/CGIT

Documentation
=============

If you found this then you presumably know where the documentation lives. If not,
look at https://cobalt-bridge.readthedocs.io.

To update the documentation look in the cobalt sub-directory docs.

This page covers common things required to set up Cobalt, there are extra steps
for the ABF version to connect to the MasterPoints server and Stripe payment gateway.
For more information go to https://abftech.atlassian.net/wiki/spaces/COBALT/pages/6225921/Setting+Up+the+Development+Environment
