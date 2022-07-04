:orphan:

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

.. image:: ../../images/development.jpg
 :width: 300
 :alt: Coding

#####################
Development Approach
#####################

This document describes some of the key factors for development of Cobalt.

*****************
Design Principles
*****************

Comments
========

Comments make code easier to understand. We aim to over-comment rather than
under-comment. Don't think of the comments as being there to explain the code to a human,
think of the code being there because the compiler cannot read the comments.

- Comment functions and classes with descriptions using """ at the top of the section
- Comment python code with # anywhere it makes sense
- Put a header at the top of each template to explain what it does. You can use `cgit_util_doc_editor` to make it easy to generate.
- Use whatever comment method you like in templates - Django ({# #}), HTML (<!-- -->), CSS (/* */), or JavaScript (//)

HTML not JSON
=============

We use HTMX wherever possible. It makes the code much easier to develop and maintain.

Avoid using Ajax and JSON to communicate with the server from the browser. Instead use
HTMX to return pre-formatted HTML to add to the DOM.

Some of the older code was built using JSON, but nothing new should follow this pattern.

For more information on why HTMX is used see :doc:`../discussion/design_overview`.

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

****************
Github Branching
****************

The documentation for this is in Confluence.

https://abftech.atlassian.net/wiki/spaces/COBALT/pages/6586408/Git+Process+for+Working+on+Jira+Tasks

There are also some support tools to assist with this. See the CGIT section in :doc:`../reference/utilities`.


=============
Documentation
=============

If you found this then you presumably know where the documentation lives. If not,
look at https://docs.myabf.com.au

To update the documentation look in the cobalt sub-directory docs.

This page covers common things required to set up Cobalt, there are extra steps
for the ABF version to connect to the MasterPoints server and Stripe payment gateway.
For more information go to https://abftech.atlassian.net/wiki/spaces/COBALT/pages/6225921/Setting+Up+the+Development+Environment
