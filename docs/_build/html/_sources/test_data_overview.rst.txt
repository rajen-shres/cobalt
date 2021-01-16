.. _forums-overview:


.. image:: images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

Test Data Overview
==================

Cobalt has scripts to generate test data. This page describes how to use them.

General Approach
----------------

The script ``utils/management/commands/add_test_data.py`` loads test data from
the directory ``utils/testdata``. The test data is in CSV format and is safe to
edit with Excel. The test data is run in alphabetical order so it can
handle dependencies between the files. Each file
matches a model within Cobalt.

The script assumes an empty but initialised database. It requires the default
Users and Org to be present as well as the RBAC static data. The standard
configuration scripts take care of this.

CSV Format
----------

The files are CSV, so commas cannot be used within text fields or the script
will fail. If you need to use a comma you can substitute it for a carat(^)
and the script will insert a comma instead.
It will ignore blank lines or lines that **start** with #. Using
a # as a comment anywhere but the first column will not work.

The first row specifies the application and model. e.g.::

  accounts,User

This is case sensitive. An optional third parameter can be provided to
specify that duplicate entries are allowed (for example, if you want to
generate multiple identical payments.)::

  accounts,User,duplicates

The second row contains the field definitions. This labels each column with the
model field that it represents. e.g. "description" or "payment_type". These
are also case sensitive. There are some specific column names which are used
as well. If the name has a dotted format such as d.created_date then the
script will use this information to understand the field type. The second part
of the name matches the model field name as described above. The following
types are used:

* d. - date
* m. - time
* t - relative date (deducts the value from today)

Additionally the special identifier ``id`` is used to denote an instance of
this model that another file may refer to. See the next section on Foreign Keys
for more details.

Foreign Keys
------------

Many of the files require links to entries in other files. If a file has an ``id``
in the first data column then this can be used by other files to refer to this
instance of that model. e.g.::

  users.csv

  id, system_number, first_name, last_name
  jj, 109,           Janet,      Jumper
  kk, 110,           Keith,      Kenneth

  member_orgs.csv

  id.member.accounts.User, id.org.organisations.Organisation
  jj,                      fbc
  jj,                      rbc

If an id is required but you don't need to refer to this field elsewhere then
you can use anything as long as it doesn't clash with something you do want to
refer to elsewhere (e.g. Dummy).

The column naming convention is::

  id.[field].[application].[model]

* id - fixed identifier
* field - the name of this field in this model
* application - the name of the other (foreign) application
* model - the name of the other (foreign) model

Payments
--------

Cobalt takes care of booking both sides of a transaction (user to org and org
to user for example). Here that does not happen so you will need to book two
transactions yourself.
