:orphan:

.. image:: ../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

.. image:: ../images/testing.jpg
 :width: 300
 :alt: Testing

Testing Overview
================

This page describes the testing strategy for Cobalt. Also see the documentation on building core test data -
:doc:`test_data_overview`.

Basics
------
We have a Test environment as well as a User Acceptance Testing (UAT) environment for the
ABF instance of Cobalt (My ABF). Either of these can be used for testing, but generally Test is used for
normal user testing by the core team and UAT is used for a wider group of people. UAT is also a core
part of the release process to check that releases will work in production.

In addition there
is a build server that can be used for automated testing.

We have two types of automated tests, Unit tests and Integration tests.

- **Unit Tests** are shorter, isolated tests that check the internal workings of the code
- **Integration Tests** are developing stories. We start by creating a user in chapter 1, in chapter 4 we create a congress and in chapter 5 the user enters the congress.

Both tests start with a basic database that has test data loaded.

Unit tests can be run in any order and do not update the database (this is handled by the test harness,
it just rolls back any changes).
Integration tests do update the database and need to run in order.

Shockingly we have our own test harness, but more on that below.

Tests work off a clean, empty database. Production
isn’t clean nor empty so we need to be careful with
changes that can affect existing production data.

User Testing
------------

* Humans can test in any environment, it doesn’t matter
* UAT is intended for use by people outside the core team, Test is intended to be internal
* Test should always run the code from the develop branch
* Production should always run the code from the master branch with a branch called release/x.x.x holding a point in time version of master
* UAT should run the candidate code for the next release
* All functionality should be supported by automatic test data than can be reset easily
* Humans should do post-install testing on production whenever possible
* Since we don't store anything particularly confidential, we can also test against copies of production data before releasing to production as data is the biggest cause of problems

Automated Testing - General
---------------------------

To run the automated tests together you can use `cgit_dev_test_all`.

This will run both types of test and also produce a coverage report. This is intended to be run
as part of the development process.

Automated Testing - Unit
---------------------------

The unit tests are generally short and work at the function level. You can run them with `cgit_dev_test_unit`.

The easiest way to build new tests is to copy existing ones. Unit tests live in `<module>/tests/unit`.

Unit tests are easier to write than integration tests and you are encouraged to write as many as possible.

Unit tests are automatically discovered but can be run in any random order.

Automated Testing - Integration
--------------------------------

There are two basic types of automated tests used:

* Selenium is used to test through the web page
* We also use the Django test client, along with direct model access and Forms to do functional testing.

Both approaches are used together, so we might use Selenium to create something and then access
the model directly to confirm it was successful.

You can run them with `cgit_dev_test_integration`.

The easiest way to build new tests is to copy existing ones. Integration tests live in `<module>/tests/integration`.

Integration tests must run in order so they are manually configured in `tests/test_manager.py`.

Performance Testing
-------------------

There are currently over 3,000 people involved in performance testing.

    "Premature optimization is the root of all evil." Sir Tony Hoare

*It is planned to add New Relic for capture and alerting around key metrics*.

Security Testing
----------------

Some of the automated tests focus on specific aspects of security and one module tests for URLs that do not
require authorisation.

Why Don't We Use a Testing Framework?
-------------------------------------

We started out with minimal testing and then added pytest. We quickly hit limitation with this and
ended up building a very simple test framework ourselves.

It is very easy to use (copy an example) and produces human readable HTML files that explain what
was tested and what the outcome was. Neither pytest nor unittest can do this.

