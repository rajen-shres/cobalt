.. _forums-overview:


.. image:: images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

Utilities Overview
==================

Generic User Search
-------------------

This is a client side utility that shows a pop up box for the user to search
for another user. In order to implement this you need to do 4 things:

1. Import the body part of the HTML into your template::

    {% include "utils/generic_user_search_body.html" with search_id=1 %}

2. Set up a button or similar HTML element to trigger the search::

    <a class="cobalt_generic_member" data-toggle="modal" id="unique_id" data-target="#cobalt_general_member_search1">Add</a>

Change 1 to whatever search_id was set to.

3. Import the footer part of the HTML into your template::

    {% block footer %}
    <script>
    {% include "utils/generic_user_search_footer.html" with search_id=1 %}

If you want to allow the user to include themselves in the
search you can add include_me=True

4. Below the block footer, set up a function to handle a user selecting another member from the list::

    function cobaltMemberSearchOk() {

    // Do whatever
    alert(member_id[1]);

    </script>
    {% endblock %}

5. There is also a callback for cancelling the search::

    function cobaltMemberSearchCancel(search_id) {
    // do something
    }

Bringing it all together to make it easier to cut and paste::

   {% include "utils/generic_user_search_body.html" with search_id=1 %}
   <a class="cobalt_generic_member" data-toggle="modal" id="unique_id" data-target="#cobalt_general_member_search1">Add</a>
   {% block footer %}
    <script>
    {% include "utils/generic_user_search_footer.html" with search_id=1 include_me=True%}
    function cobaltMemberSearchOk() {

    // Do whatever
    alert(member_id[1]);

    </script>
    {% endblock %}

Pagination Footer
-----------------

To use the same pagination footer (Next Page, Previous Page, etc at the bottom of a screen that is too big to show everything on one page.),
you can use::

  {% include 'pagination_footer.html' %}

Your list must be called 'things' for this to work.

If you are paginating over a search list you will need to supply your search string as well. e.g.::

    user = request.GET.get("author")
    title = request.GET.get("title")
    forum = request.GET.get("forum")
    searchparams = "author=%s&title=%s&forum=%s&" % (user, title, forum)

    return render(
        request,
        "forums/post_search.html",
        {"filter": post_filter, "things": response, "searchparams": searchparams},
    )

Pagination Formatter
--------------------

Pagination in views is a common thing so we have a central utility for it::

    from utils.utils import cobalt_paginator

    my_list = ["some", "list", "to", "paginate"]
    items_per_page = 20
    things = cobalt_paginator(request, my_list, items_per_page)
    return render(request, "mypage.html" {"things": things})

Unsaved Changes
---------------

Lots of forms need to handle users navigating away from the page without saving
changes. We have a JavaScript function to handle this::

    <script src="{% static "assets/js/cobalt-unsaved.js" %}"></script>

You also need to identify which buttons are *save* buttons and should be
ignored if pressed (i.e. don't warn the user about navigating away with unsaved
changes). Do this using the class cobalt-save::

    <button type="submit" name="Save" class="cobalt-save btn btn-success">Save</button>

As this is loaded by default you need a way to tell it to ignore your page.

You can do this by adding any element with the id ignore_cobalt_save. e.g.::

    <div id="ignore_cobalt_save"></div>

Template Filters
----------------

You can use the following template filters::

  {% load cobalt_tags %}

      {{ my_date_or_datetime|cobalt_nice_date }}

      e.g. Saturday 7th May 2022

      {{ my_time_or_datetime|cobalt_time }}

      e.g. 10am or 7:35pm

      {{ my_datetime|cobalt_nice_datetime }}

      e.g. Saturday 7th May 2022 11:32am

      {{ request.user|cobalt_user_link }}

      prints user with a link to their public profile. e.g.
          <a href='/accounts/public_profile/45'>Peter Parker(45654)</a>

Size Based Text
===============

If you want to have different text based upon the size of the screen
(or anything else based on the size of the screen), you can use this::

    <!-- Show on large screens, not small -->
    <span class="d-none d-md-block d-lg-block">
      Administration
    </span>
    <!-- Show on small screens, not large -->
    <span class="d-md-none d-lg-none d-xl-none d-xs-block d-sm-block">
      Admin
    </span>


Batch Jobs
==========

Cobalt uses django-extensions
`django-extensions <https://django-extensions.readthedocs.io/en/latest/jobs_scheduling.html>`_.
to handle batch jobs. This allows us to have batch jobs defined within the applications
to which they correspond.

Django-extensions creates a structure for us, e.g.::

  cobalt\
        events\
              jobs\
                hourly\
                  hourly_job_1.py
                  hourly_job_2.py
                daily\
                  my_daily_job.py
                weekly\
                monthly\
                yearly\

You can follow the examples to create new jobs.

Multi-Node Environments
-----------------------

We generally only want the batch to run once so in a multi-node environment
such as AWS we need to make sure the batch doesn't run on all nodes. We can
do this with a Cobalt utility::

  from utils.views import CobaltBatch
  from django_extensions.management.jobs import DailyJob

  class Job(DailyJob):
      help = "Cache (db) cleanup Job"

      def execute(self):

        batch = CobaltBatch(name="My batch run", instance=5, schedule="Hourly" rerun=False)
  # instance is optional and only needed if you run multiple times per day

        if batch.start():

  # run your commands

          batch.finished(status="Success")
  #        batch.finished(status="Failed")

As well as recording the start and end times of the batch job, CobaltBatch
ensures that only one job per day per instance can be run. It does this by
sleeping for a random time to avoid conflict and returning false for any
subsequent job that tries to start. You can override this by specifying
rerun=True (I don't know how yet!).

Running Batch Jobs
------------------

You need to run batch jobs from cron::

  manage.py runjobs daily

For Elastic Beanstalk this can be set up with an install script.

AWS Utilities
=============

These are specific to the ABF implementation of Cobalt but can be modified
for use on any other installation that uses AWS Elastic Beanstalk.

These commands also rely upon the configuration files and scripts that live in
``.ebextensions`` and ``.platform``.

cobalt_aws_create_environment.py
--------------------------------

Creates a new Elastic Beanstalk environment including DNS entries. This requires
a config file with the environment variables which for obvious security reasons
is not kept within Github.

For usage run::

  python cobalt_aws_create_environment.py -h

For example::

  python cobalt_aws_create_environment.py cobalt-uat-pink /tmp/cobalt-uat.env --env_type uat -d uat3

  EB Environment Name: cobalt-uat-pink
  Input config file: /tmp/cobalt-uat.env
  Environment type: UAT
  DNS name: uat3.abftech.com.au

The most useful option is ``--env_type standalone`` which creates an environment
with a local sqlite3 database. This won't interfere with any other environment and
can be used for specific testing. Note that creating a test or uat environment will
replace the existing data in those databases with the default test data.

This script uses ssh to connect to the instance to complete set up. This is only
intended for single node clusters and is not used for production systems which
must set up their own environments. As ssh is used you will be prompted to
confirm the first time connection. You can remove this check (not recommended
unless you are okay with no server checking which can allow a man-in-the-middle
attack) by adding this to your .ssh/config::

  Host *
   StrictHostKeyChecking no
   UserKnownHostsFile=/dev/null

CGIT
====

Cgit is a bunch of scripts to make working with Git and Elastic
Beanstalk easier. They are not a required part of Cobalt, but they do
live within the Cobalt source code inside utils (utils/cgit - you
can add this to your path or copy the files to somewhere on your path,
it is up to you).

Cgit only really runs on a Mac.

Installation
------------

Set up your path (or copy files) and you should be able to run::

    cgit_help

This should get you started. If you don't already have the EB CLI tool,
the AWSCLI tool and git installed then you will have problems.

Additionally you need to install a diff viewer to use the reporting::

    sudo npm install -g diff2html-cli

Usage
-----

cgit_help provides a list of all of the commands. They should be used in order.

Cgit adds descriptions to the Elastic Beanstalk releases so it can
know exactly what is installed in each system. If you release without
using cgit try to include this information anyway if you can::

    eb deploy -m "<branch>@<YYYY.MM.DD:HH:MM>"

cgit_dev_start
^^^^^^^^^^^^^^

.. code-block:: bash

  $ cgit_dev_start mine

**Purpose**: Creates a new development branch

**Git Impact**: Creates temporary development branch

**Environment Impact**: None

cgit_dev_save
^^^^^^^^^^^^^

.. code-block:: bash

  $ cgit_dev_save "My comment"

**Purpose**: Saves local changes to Github server

**Git Impact**: Updates Github branch with local changes

**Environment Impact**: None

cgit_dev_finish
^^^^^^^^^^^^^^^

.. code-block:: bash

  $ cgit_dev_finish

**Purpose**: Completes this work and updates develop branch and Test system

**Git Impact**: Updates develop branch. Deletes temporary branch.

**Environment Impact**: Updates Test with latest develop branch

cgit_uat_publish
^^^^^^^^^^^^^^^^

.. code-block:: bash

  $ cgit_uat_publish

**Purpose**: Push changes to UAT system

**Git Impact**: Creates release branch with new number, release/x.y.z.

**Environment Impact**: Updates UAT with release/x.y.z

cgit_uat_fix_start
^^^^^^^^^^^^^^^^^^

.. code-block:: bash

  $ cgit_uat_fix_start release/x.y.z myfix

**Purpose**: Creates a new branch to fix the code in UAT without pulling code from development.

**Git Impact**: Creates temporary fix branch release/x.y.z=myfix

**Environment Impact**: None

cgit_uat_fix_save
^^^^^^^^^^^^^^^^^

Same as cgit_dev_save, saves current branch to Github server

cgit_uat_fix_finish
^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

  $ cgit_uat_fix_finish

**Purpose**: Patches UAT

**Git Impact**: Updates release/x.y.z with fix. Deletes fix branch. Merges changes into develop.

**Environment Impact**: Updates UAT with patched release/x.y.z

cgit_prod_publish
^^^^^^^^^^^^^^^^^

.. code-block:: bash

  $ cgit_prod_publish

**Purpose**: Deploys release/x.y.z to production

**Git Impact**: None

**Environment Impact**: Updates Production with release/x.y.z


cgit_prod_hotfix_start
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

  $ cgit_prod_hotfix_start release/x.y.z myhotfix

**Purpose**: Starts working on a hotfix to go straight into production.

**Git Impact**: Creates branch release/x.y.z=hotfix=myhotfix

**Environment Impact**: None

cgit_prod_hotfix_save
^^^^^^^^^^^^^^^^^^^^^

Same as cgit_dev_save, saves current branch to Github server


cgit_prod_hotfix_test
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

  $ cgit_prod_hotfix_test

**Purpose**: Releases hotfix branch to a test server (by default Test)

**Git Impact**: None

**Environment Impact**: Updates Test (or specified environment) with hotfix version. **Note**: Test may be ahead of Production in terms of migrations.

cgit_prod_hotfix_finish
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

  $ cgit_prod_hotfix_finish

**Purpose**: Patches release branch and deploys to Production.

**Git Impact**: Merges patch into release/x.y.z. Deletes patch branch.

**Environment Impact**: Updates production with hotfixed version release/z.y.z..

Mapping Branches to AWS Descriptions
------------------------------------

In test the branch will normally be develop, unless test has been used
to trial a fix before releasing to another environment. The AWS
description will be develop@<time>.

In UAT or Production the description will be release/x.y.z@<time> or
release/x.y.z-fixlabel@<time>. This will always match with the Github
branch release/x.y.z which is patched whenever a fix is deployed. The
extra part of the label is useful for knowing what the latest patch
applied was.