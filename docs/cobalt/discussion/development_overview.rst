:orphan:

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

.. image:: ../../images/development.jpg
 :width: 300
 :alt: Coding

Development Approach (edit)
===========================


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
