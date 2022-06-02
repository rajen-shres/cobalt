:orphan:

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

.. image:: ../../images/development.jpg
 :width: 300
 :alt: Coding

===============
Getting Started
===============

In this tutorial you will learn how to install Cobalt and configure it
to run in your development environment on your personal computer.

.. note::

    This tutorial is designed for a Mac or Linux development environment.
    If you want to develop on Windows you will need to install the Windows Linux Subsystem. File
    permissions and other things get messed up in the Windows UI so it is not recommended.

    You can use Pycharm or VS Code, or whatever IDE you like to do your work, you just need
    to run git and the other tools through WLS.

    Once you have installed WLS you can follow all of the steps in this tutorial on Windows.

Pre-requisites
==============

Before you start you will need to install:

- Python 3 (>3.5)
- Pip
- Virtualenv
- Git
- Postgres

There are plenty of internet resources for this and they change with time, so we
don't include instructions on this here. Once you have the pre-requisites installed,
you are ready to start this tutorial.

Goals
=====

By the end of this tutorial you will understand:

- Cobalt dependencies
- How to install the stripe CLI (used for payments)
- Setting required environment variables
- Cobalt static data and how to load it through Django management commands
- Cobalt test data and how to load it into an empty but initialised database

Step 1 - Installing Cobalt
==========================

Open a terminal window and navigate to the location you would like to install Cobalt.
Cobalt doesn't care which directory it gets installed into.

Virtual Environment
-------------------

Run these commands to create your project directory and initialise your virtual environment.
We are calling the directory cobalt-project, but you can call it whatever you like::

    $ mkdir cobalt-project
    $ virtualenv myenv   # specify -P python3.7 or similar if that is not your default
    $ . ./myenv/bin/activate
    $ mkdir cobalt
    $ cd cobalt

Download the Code
-----------------

Get code from github and set up::

    $ git init
    $ git remote add origin https://github.com/abftech/cobalt.git
    $ git pull origin master

Install Packages
----------------

Cobalt relies on a number of standard Python packages which can be downloaded using pip::

    $ pip install -r requirements.txt

Cobalt also uses some development-only packages which you can install by running::

    $ pip install -r requirements-dev.txt

We use a number of pre-commits to ensure the quality of the code being checked back into
the repository. You won't need these for this tutorial, but it is good practice to install
them which you can do using this command::

    $ pre-commit install

.. important::
    On a Mac you need to install one more file into your virtual environment. You will need to
    know what version of Python you are running and whether you are on an Intel or M1 machine.

    To find the version of Python you can type python -V, you only need the first two numbers,
    e.g. if you are on Python 3.7.9 you only need to use 3.7.

    On an M1 Mac:

    cp utils/bin/M1/libdds.so ../myenv/lib/python<YOUR VERSION HERE>/site-packages/ddstable/libdds.so

    On an Intel Mac:

    cp utils/bin/Intel/libdds.so ../myenv/lib/python<YOUR VERSION HERE>/site-packages/ddstable/libdds.so


Step 2 - Environment Variables
==============================

Cobalt uses environment variables to specify values that may change between environments
such as database names and credentials.

For a full list of environment variables you can refer to: :doc:`../environment_variables`.

Create a file called something like cobalt_env.sh and add this to the file::

    export DEBUG=True
    export RDS_DB_NAME=ebdb
    export RDS_HOSTNAME=127.0.0.1
    # Change next line if Postgres is running on a different port
    export RDS_PORT=5432
    export RDS_USERNAME=cobalt
    # Change next line if you want to use a different password
    export RDS_PASSWORD=F1shcake
    export GLOBAL_MPSERVER=http://masterpoints-test-black.ap-southeast-2.elasticbeanstalk.com

Now you can source this file to add the variables to your environment::

    $ . /path/to/my/file/cobalt_env.sh

Step 3 - Configure the Database
===============================

If you haven't already installed Postgres on your system, you need to do so now.

First, we need to create a user for Cobalt. Start psql, either from the command prompt or through any other means::

    postgres=# create user cobalt with encrypted password 'F1shcake';

Instead of 'F1shcake' you can choose whatever password you like. Within the ABF
version of Cobalt we use 'F1shcake' as the standard development password for all
accounts where security is not required. As long as this password matches the value
you used in your environment variables for RDS_PASSWORD, that is fine.

Now, still within psql, we need to create a new database::

    postgres=# create database ebdb with owner cobalt;

Again, the database name can be changed as long as it matches the environment variable
RDS_DB_NAME.

You can exit out of psql now, we won't need it any more.

Step 4 - Test Database Connection
=================================

We have covered quite a lot already, but we haven't checked if any of it is working. Before we go on we will
test that we can talk to the database.

The database is completely empty and we can use a Django command to initialise it. If this has a problem, it will
almost certainly be due to not connecting to the database. Django's errors are very good and should help you
to fix the problem if you have one.

Activate your virtual environment, source your environment variables and make sure you are in your
Cobalt directory. e.g. cobalt_project/cobalt. This should all be in place if you followed the steps above.

Now run the following command::

    $ ./manage.py migrate

If all is well then you should see messages similar to the following::

    Operations to perform:
      Apply all migrations: accounts, admin, api, auth, club_sessions, contenttypes, django_ses, django_summernote, events, fcm_django, forums, logs, masterpoints, notifications, organisations, otp_totp, payments, post_office, rbac, sessions, support, utils
    Running migrations:
      Applying contenttypes.0001_initial... OK
      Applying contenttypes.0002_remove_content_type_name... OK
      Applying auth.0001_initial... OK
      Applying auth.0002_alter_permission_name_max_length... OK
      <truncated>
      Applying utils.0006_alter_lock_lock_open_time... OK
      Applying utils.0007_slug... OK
      Applying utils.0008_alter_slug_slug... OK

If you don't see this, then something has gone wrong and you need to review the errors and fix it before you can continue.

Step 5 - Management Commands
============================

So far you have downloaded Cobalt, set up the environment variables that it needs and
connected it to the database. The command you ran above (``./manage.py migrate``) created
all of the database tables that Cobalt needs, but Cobalt additionally stores some static
and reference data in the database and won't be able to start without it.

The ABF version of Cobalt is deployed on Amazon Web Services (AWS). You aren't using AWS in your
development environment and in fact you don't need to in a production environment either.
However, the commands that are run in AWS to set up the static data for Cobalt are exactly the
same commands that you need to run now. AWS insists on these commands being in a particular location
and as we don't want to maintain two copies of the commands we will use the AWS copy now.

Run::

    $ .platform/hooks/postdeploy/02_django.sh.


Step 6 - Test Data
------------------

.. hint::
    This step is optional. You can skip it and login at Step 7 using the username "Mark" and password "F1shcake",
    however the system will be completely blank, but usable.

To load the standard test data into Cobalt, run this command::

    $ utils/aws/rebuild_test_database_subcommands.sh

Step 7 - Starting Cobalt
========================

Now you are ready to run Cobalt::

    $ ./manage.py runserver

Once it starts you can open a browser to http://127.0.0.01:8000.

If everything is successful then you should see the logged out welcome page. You can login as any of the test users.
The username for the test users ranges from "100" to "124" and the password defaults to "F1shcake".

Next Steps
==========

Congratulations! You now have a working Cobalt system.

However, you will notice that some of the optional features are missing. To add them, you can follow these other guides:

- Adding Email to Cobalt
- Adding Stripe Payments to Cobalt
- Adding SMS
- Adding FCM
- Adding Google Recaptcha