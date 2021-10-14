:orphan:

.. image:: images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

Utilities Overview
==================

Generic User Search
-------------------

This replaces the original generic user search which is still in the
documentation below to allow supporting older code within Cobalt.

This is the preferred version for all new work.

The user search uses HTMX for a much cleaner coding experience.

To use it, add the following to your HTML template::

    {% block footer %}
    {% include "utils/include_htmx.html" %}
     {% include "accounts/user_search_include_htmx.html" with search_id={{ search_id}} include_me=True callback="MyFunc" %}

    <script>
        function MyFunc(search_id, user_id, user_name){
        // do something
            console.log(search_id);
            console.log(user_id);
            console.log(user_name);
        }
    </script>
    {% endblock footer %}

To call it add a line to your HTML body::

   <button type="button" class="btn btn-info" data-toggle="modal" data-target="#userSearchModal{{ search_id }}">Add</button>

Drop the include_me option if you do not want the logged in user to be included in the search results.

The user search dynamically adds functions using HTMX (https://htmx.org).

Originally it was intended to be able to work inline and to return a div with the name of the user, the hidden
input and a button to search again. In practice only the callback version has been used so far. The code is
still there to support the inline version (include search_include_inline_htmx.html if you want to use it),
but it was never finished or tested.

Design
^^^^^^

If you have to support this, here is how it works.

It starts with user_search_include_htmx.html which has the modal and the HTMX calls to load the next parts. The bottom
of the modal has a div that gets populated with the response from the server, either the user that is found or errors,
or for the name searches a list of matches.

The modal is brought to the front by the button in the calling code.

The searches and templates are:

URL
accounts:member_search_htmx

.. list-table:: Other Components
   :header-rows: 1

   * - URL
     - View
     - Template
   * - views.member_search_htmx
     - views.member_search_htmx
     - member_search_htmx.html
   * - system_number_search_htmx
     - system_number_search_htmx
     - name_match_htmx.html
   * - member_match_htmx
     - member_match_htmx
     - name_match_htmx.html

System_number_search returns the member_match template if it finds a match or sends an error itself.

With HTMX avoid adding Javascript dynamically over HTMX as it can be problematic. Here we use static Javascript
functions which are loaded with the main page.

Generic User Search - Old. Do Not Use
-------------------------------------

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

Delete Modal
------------

You often want to warn a user that they are about to delete something.
The delete modal (using HTMX) can handle this for you, e.g.::

    <ul>
        {% for user in users %}
            <li>{{ user }}
                {% include "utils/htmx_delete_modal.html" with id=user.id delete_item=user.first_name hx_target="#access-basic" hx_post=user.hx_post %}
                <button type="button" class="btn btn-sm btn-danger" data-toggle="modal" data-target="#deleteModal{{ user.id }}">
                    Delete
                </button>
            </li>
        {% endfor %}
    </ul>

hx_target specifies which CSS identifier to replace with the results.

You can specify either delete_item, which will be inserted into a generic string, or
delete_message which will totally replace the generic string.

You need to add an attribute to your list of objects called hx_post to
define what the url should be for the delete action. You can do this in
your code with something like::

    for user in users:
        user.hx_post = reverse(
            "organisations:club_admin_access_basic_delete_user_htmx",
            kwargs={"club_id": club.id, "user_id": user.id},
        )

Usually hx_target will point to your list that includes the item you
are deleting and your delete function needs to return a replacement list.
When building the list initially you should separate the list code
into a separate HTMX.HTML document and include it so that the list code
is re-used by the initial and the replace (delete) functionality.

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


Cobalt Simple Form
==================

If you want a simple Bootstrap4 form and don't need to customise the field set up, you can use this::

        <form method="post" novalidate>
          {% csrf_token %}
          {% include 'utils/cobalt_simple_form.html' with form=my_form %}
          <button type="submit" class="btn btn-primary">Submit</button>
        </form>


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
Cgit_help also shows the current versions installed in each environment.

Cgit adds descriptions to the Elastic Beanstalk releases so it can
know exactly what is installed in each system. If you release without
using cgit try to include this information anyway if you can::

    eb deploy -m "<branch>@Sun_12/07/21_08:05"



cgit_compare
^^^^^^^^^^^^

.. code-block:: bash

  $ cgit_compare production

**Purpose**: Compares the current branch with test, UAT or production.

**Git Impact**: None

**Environment Impact**: None

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

**Environment Impact**: Updates production with hotfixed version release/z.y.z.

Mapping Branches to AWS Descriptions
------------------------------------

In test the branch will normally be develop, unless test has been used
to trial a fix before releasing to another environment. The AWS
description will be develop@<time>.

In UAT the description will be release/x.y.z@<time>.
This will always match with the Github
branch release/x.y.z which is patched whenever a fix is deployed.

In Production the description will be release/x.y.z@<time> or
release/x.y.z--fixlabel@<time>. This will always match with the Github
branch release/x.y.z which is patched whenever a fix is deployed. The
extra part of the label is useful for knowing what the latest patch
applied was. The branch release/x.y.z--fixlabel is kept for tracking
purposes and will be identical to release/x.y.z when the hotfix is
applied. Subsequently it can get out of step.