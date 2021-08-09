.. _forums-overview:


.. image:: images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

Testing Overview
================

This page describes the testing strategy for Cobalt.
Its not intended to be an essay on testing in general
but just some practical information on how to approach
testing in Cobalt.

Basics
------
We aren’t using Test Driven Development. While it
is not a bad idea, it also isn’t particularly
practical and I’ve never seen it work.

The most important testing is done by humans.
User testing can happen in either the Test or
UAT environment, it doesn’t really matter,
but all changes should be tested by people.
The system is too large for regular regression
tests to be performed so targeted testing
is done for each change. Yes, this means that
unforeseen consequences can get to production
because they were not tested but it is the job
of the developer to point out to the tester if
they think there is a chance that something else
might be affected and for the tester to take that
into account when performing the testing.

Automated testing exists to catch major issues.
The automated test suite is run on the build server
every time code is checked into the develop branch.
The fundamental principle with automated testing is
to keep it simple, not to worry about the UI, and
to test a lot of common things rather than a few
rare things. Payments gets priority.

Tests work off a clean, empty database. Production
isn’t clean nor empty so we need to be careful with
changes that can affect existing production data.

User Testing
------------

* Humans can test in any environment, it doesn’t matter
* UAT is intended for use by people outside the core team, Test is intended to be internal
* Test should always run the code from the develop branch
* Production should always run the code from the master branch
* UAT should run the candidate code for the next release
* All functionality should be supported by automatic test data than can be reset easily
* Humans should do post-install testing on production whenever possible

Automated Testing
-----------------

There are two basic types of automated tests used:

* Selenium is used to test through the web page
* We also use the Django test client, along with direct model access and Forms to do functional testing.

Both approaches are used together, so a we might use Selenium to create something and then access
the model directly to confirm it was successful.

Performance Testing
-------------------

We don’t do anything.

Security Testing
----------------

We don’t do anything.

Why Don't We Use a Testing Framework?
-------------------------------------

Both Django and Python itself come with large
testing frameworks. While we use the Django test
client module, we don't use Unittest or pytest.
The reason for this is that our testing is fairly
simplistic and doesn't need a large framework. The original author
was not familiar with either framework (or any of
the others) so the learning curve would have been
greater than the effort required to implement a
simple solution ourselves. This won't be good news
for whoever is maintaining this if you already know
these frameworks, but our approach is so simple
that it shouldn't be hard for you.

Running Tests
=============

Most of the testing is done in the development environment,
with the build server running confirmation tests when code
is committed to develop.

The testing scripts assume you are running on a Mac
and have set up command windows to run the server and the
Stripe client. You can take the commands from the script
and run them separately if this is not the case.

cgit_dev_test
-------------

This is the wrapper script to start the tests. it does the following:

* Rebuilds the test database (the ebdb database is not touched by testing)
* Sets the RDS_DB_NAME to "test"
* Sets the port to 8088 (usually development runs on 8000 so there is no conflict)
* Starts the Mac Terminal Window Group "testing" which should be set to run two windows. One for ./manage runserver on port 8088 and one for Stripe connecting to port 8088.
* After a keypress to confirm the windows are running it will run::

    ./manage.py run_tests --base_url http://127.0.0.1:$PORT --headless true

run_tests.py management command
-------------------------------

run_tests just starts the tests off and when they complete it launches a web browser to display the results.

test_manager.py
---------------

The CobaltTestManager class within test_manager.py orchestrates the testing. It has a list of tests to run and calls
those classes in order. It provides a basic environment for each test to be able to run, including users, login
commands and Selenium scripts and a common way to report how the test worked.


