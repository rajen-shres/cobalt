:orphan:

.. image:: ../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

.. image:: ../images/development.jpg
 :width: 300
 :alt: Coding

Development Overview
====================

Cobalt is written in Django. It is assumed that you already know Python,
Django and the associated tools such as ``pip`` and ``virtualenv``. If you don't
there are lots of resources available to help you.

Before you get started make sure you have the following installed:

- Python 3.7+
- pip
- virtualenv
- git
- postgres (*optional but highly recommended*)

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

.. hint::

    If you want to develop on Windows you will need to install the Windows Linux Subsystem. File
    permissions and other things get messed up in the Windows UI so it is not recommended.

    In fact, you will likely break important things for others if you try to do native Windows
    development. Don't worry though, you can use Pycharm or VS Code to do your work, you just need
    to run git and the other tools through WLS.

Here are the basic steps to get started::

    $ mkdir cobalt-project
    $ virtualenv myenv   # specify -P python3.7 or similar if that is not your default
    $ . ./myenv/bin/activate
    $ mkdir cobalt
    $ cd cobalt

Get code from github and set up::

    $ git init
    $ git remote add origin https://github.com/abftech/cobalt.git
    $ git pull origin develop

Install requirements::

    $ pip install -r requirements.txt

Install development-only requirements::

    $ pip install -r requirements-dev.txt

We recommend using pre-commits for Git which are described below. For now,
just install them using::

    $ pre-commit install

Database
--------

There are a number of problems with using SQLite3 especially on a Mac. It is
strongly recommended that even for development, you set up a local Postgres
database.

You will need to create a user. Start psql::

    postgres=# create user cobalt with encrypted password 'password';

Environment Variables
---------------------

See main article: :doc:`environment_variables`.

Before running manage.py you will need to set some environment variables. As these are considered secret they
are not part of the codebase, but you should be able to get help from another developer.

It is easiest to put these in a batch file, or even run it automatically when
you start your shell.

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
The input is CSV files which live in ``tests/test_data``.

Combining it all
----------------

As a developer you will find yourself rebuilding the database quite often.
You can use a script to automate this for you.

For example::

    #!/bin/sh

    # reset database
    psql -f rebuild_dev_db.sql

    # migrate
    ./manage.py migrate

    # static data
    utils/aws/rebuild_test_database_subcommands.sh

    # Test data
    ./manage.py add_test_data

rebuild_dev_db.sql::

    \c postgres
    drop database ebdb;
    create database ebdb with owner cobalt;

Design Principles
=================

Comments
--------

A lot of programmers view comments in code as a sign of weakness.

*"You are obviously
a very poor programmer if you can't work out what it does from the code alone."*

There are two main reasons why you will be looking at the code after
it has been completed:

#. It doesn't do what it is supposed to do (bug)
#. It doesn't do what it now needs to do (enhancement)

In neither case will you be very happy if the bare code is all you have to help you.

   **Comment your code, you might be the poor bugger who has to support it**

It is often thought that the comments are there to explain the code to a programmer.
In fact it should be the opposite. The code is there to explain the comments
to the computer.

HTML not JSON
-------------

Django is very good at producing HTML but merely average at producing JSON. In
Cobalt we prefer to have Django produce formatted HTML that can be replaced
on the page rather than JSON that we have to format in the client. This
isn't what all the smart people who write articles about Django say, but they
are wrong. Even if they are right, it's not the way we do it in Cobalt and
consistency is more important than perfection.

There is still some code in Cobalt that uses JSON (we listened to the
experts at the beginning before working it out for ourselves). Feel free to replace it with
HTML as you go.

We use HTMX to swap out one bit of HTML for another using Ajax. It is a
small and fairly simple library. If you find something that you can't do using
HTMX, that is okay. Use JQuery but make the payload HTML not JSON and replace it
directly into a DIV.

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
