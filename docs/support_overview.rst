:orphan:

.. image:: images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

Support Overview
================

Support currently is quite simple. The only more
difficult part is the Helpdesk module.

Helpdesk - Why?
---------------

The initial release of Cobalt had a simple form to
allow a user to report a problem. This was sent
to the ADMIN setting in settings.py. As support
requests increased this proved to be unworkable. You
wouldn't know if everyone had replied to a user or
nobody and there was no ability to track trends or
provide any stats.

We looked at using the Jira Service Desk module but
the API was poor and it would be yet another tool for
users to learn and for us to have to manage access
etc.

There were no obvious Open Source candidates and
our requirements are simple so we built it ourselves.

Helpdesk - Benefits
-------------------

* Relatively simple code.
* Custom built for our requirements.
* Fully integrated with Cobalt including RBAC.
* Consistent interface for support users.

Helpdesk - Key Features
-----------------------

* Code mostly lives in support/helpdesk.py.
* Users and notifications are separated. Users of the system are controlled by the RBAC role "support.helpdesk.edit", notifications are controlled by the model NotifyUserByType. There is currently no UI for this. Use the Django admin pages.
* Users can only see their own tickets.
* Users who have had a ticket raised get an extra link in the top right of every screen.
* It is possible to subscribe a user to a sub-set of ticket types. E.g. Only get notified about refund requests.
