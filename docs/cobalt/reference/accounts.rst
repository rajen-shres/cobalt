:orphan:

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

.. image:: ../../images/accounts.jpg
 :width: 300
 :alt: Accounts

====================
Accounts Application
====================

Module Purpose
==============

Account handles things relating to User accounts such as profiles and settings.
There are multiple user types to support the need to deal with users who have not
registered for the system as well as real, registered users.

External Usage
==============
*This section covers what you need to know to use this application from other parts of the system.*

``accounts.models.User`` is equivalent to ``request.user`` and is used throughout the
system for standard Django activities. ``accounts.models.User`` is a very widely used
foreign key.

We are in the process of moving some of the less commonly used attributes from
``accounts.models.User`` into ``accounts.models.UserAdditionalInfo`` so you may need
to load this for some fields.

Reserved Users
--------------

There are three special users within the system:

EVERYONE
    This is used mainly by RBAC for assigning security to all users.
TBA
    The *To Be Advised* user is a placeholder user mainly used by Events to hold a place in an entry until the actual player is identified.
ABF_USER
    This is the system user and is used when we want something to appear to have been done by the system rather than any individual.

If you wish to exclude (or include) system accounts, you can get a list of them from
``settings.ALL_SYSTEM_ACCOUNTS``.

User Search
-----------

**GOES HERE**

Internal Operation
==================
*This section describes the internal workings of this application and is intended to help you if you need to support the code.*

User Types
----------

We support three kinds of users:

* **Users** - These are full users of Cobalt and have signed up themselves.
* **UnregisteredUsers** - These are second class citizens used mainly by Organisations.
* **Visitors** - These are not ABF Members and are supported only for completeness for clubs.

User Objects
------------

Accounts.models.User reflects a User who can login to the system and
perform bridge functions. Some users are reserved - we have an EVERYONE
user that is used by RBAC and a TBA user that is used by Events. With hindsight
we should have reserved a few other low numbered users however, the actual
numbers (primary keys) used doesn't really matter, it will just be another
environment variable for the test environments.

We allow users to share email addresses. The first user to register an
email address can login using this email or using their ABF System Number.
Subsequent users with the same email address can only login with their
ABF System Number.

Unregistered Users
------------------

Accounts also supports a pseudo-user through the UnregisteredUser class.

This represents a user with a legitimate ABF System Number but someone
who has not yet registered themselves as a user of Cobalt. Typically
this is used when a club wants to set up their users but doesn't want
to have to ask all of them to register before it does. This is a placeholder
user which is replaced when the real user finally registers for the system.

To encourage users to register, only a basic set of things can be done
with Unregistered Users. They cannot receive results or enter events
for example.

This was put in place to allow clubs to import their member list and to
email their existing lists from within Cobalt with the minimal amount
of effort.

Emails sent to Unregistered Users have a link to allow them to register.

The key that identifies users is the ABF System Number.

* Users can only be full Users or Unregistered users, they cannot be both. The registration process ensures that when a user registers, all information is cut across from the Unregistered User which is then deleted.
* There can be only zero or one occurrences of an ABF System Number across Users and Unregistered Users.
* The Masterpoints Centre is the system of truth for mapping ABF System Numbers to first and last names, however users (the registered kind) may change this within Cobalt if they wish after registration.

Models that need to support both Users and Unregistered Users are required to do
this work themselves. They need to use system_id as the primary identifier and
handle Accounts informing them of users changing from Unregistered Users to
Users (this is done effectively with a callback in the registration view
of Accounts).

Visitors
--------

Visitors are identified by their email address. They cannot see results
or use the Cobalt website at all. We could consider emailing them
the results though.