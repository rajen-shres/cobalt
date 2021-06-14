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

There are three types of automated tests used:

* UI - we use Pylenium (front end to Selenium) to test through the web page
* Client - we test through client objects to simulate logged in users
* Model - we create and manipulate objects through the model interfaces

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

Client Testing
==============

The Client tests assume a clean database with the
test data loaded. If you change the test data there
is a good change you will break the Client tests.

To run the client tests we use a standard Django
management command::

    ./manage.py run_tests

The tests are built as classes within tests/client_test.py

This will not run on the MyABF production server, but
would be a bad thing if it ran on any production
server so be careful.

