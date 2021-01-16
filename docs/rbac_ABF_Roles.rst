.. _rbac_ABF_Roles:


.. image:: images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

 .. important::

   This document has largely been replaced by a screen within Cobalt that
   shows the data dynamically. Information in here is likely out of date.

   `ABF Test System RBAC Static <https://test.abftech.com.au/rbac/role-view>`_.

RBAC ABF Roles
==============

This page lists the roles and groups that are set up for the ABF version
of Cobalt. See `rbac_overview` for details on the module itself.

The tree structure (both the RBAC tree and the Admin tree) are only to
provide an organised way to manage a potential large number of groups.
They do not affect the security in any way. The only thing that really matters
in terms of controlling access is the roles that are added to a group and the
user who are members of that group.

This page lists the roles required for different functions and then also
the groups (and their location in the tree) that have been set up to accomodate
this.

RBAC Defaults
-------------

Defaults apply when no matching rule can be found.

* forums.forum - Allow
* forums.forumadmin - Block
* payments.global - Block
* payments.org - Block
* org.org - Block

Hierarchy
---------

Roles can be one of two main formats:

* app.model.action e.g. forums.forum.view
* app.model.model_id.action e.g. forums.forums.6.view

The higher level role (without the number) will also apply to the lower level
when checking. So for example if a user needs forums.forum.5.create for an
action, then if they have forums.forum.create that will be used. However,
specific rules have precedence. e.g. if a user has forums.forums.create Block,
and forums.forums.5.create Allow, then they will be allowed to post in forum 5.

The forum numbers (and other model_ids) are the internal representation of the
model (primary key). If necessary they can be mapped to a name, but for RBAC
it is more efficient to use the number.

RBAC All
--------

A role of "All" matches on any action. e.g. if a group has forums.forum.all
it will match against forums.forum.create or forums.forum.5.view (specifically for
forums, moderate is done a little differently and is excluded from all).

RBAC EVERYONE
-------------

The EVERYONE user matches against any user, so adding EVERYONE to a group is
the same as individually adding all users to the group.

Key Roles
=========

Forums
------

The following roles are important:

* **forums.forumadmin** [*Allow*] - allows the management of forums, e.g. create, modify and
  delete.

* **forums.forum.view** [*Allow*] - can view posts in any forum

* **forums.forum.create** [*Allow*] - can create posts or respond to posts in any forum

* **forums.forum.moderate** [*Allow*] - can moderate in any forum. Moderators can
  edit any post or comment (not delete them) and can block users from posting
  in a specific forum.

* **forums.forum.N.view** [*Allow*] - can view posts in forum N.

* **forums.forum.N.create** [*Allow*] - can create posts or respond to posts in forum N.

* **forums.forum.moderate** [*Allow*] - can moderate in forum N. Moderators can
  edit any post or comment (not delete them) and can block users from posting
  in a specific forum.

Payments
--------

* **payments.org.view** [*Allow*] - can view statements for all organisations.

* **payments.org.N.view** [*Allow*] - can view statements for organisation N.

* **payments.org.manage** [*Allow*] - can manage payments for all organisations.

* **payments.org.N.manage** [*Allow*] - can manage payments for organisation N.

* **payments.global.view** [*Allow*] - can view payments for the ABF.

* **payments.global.manage** [*Allow*] - can manage payments for the ABF.

Organisations
-------------

* **orgs.org.view** [*Allow*] - can view details about all organisations.

* **orgs.org.N.view** [*Allow*] - can view details about organisation N.

* **orgs.org.edit** [*Allow*] - can edit details about all organisations.

* **orgs.org.N.edit** [*Allow*] - can edit details about organisation N.

Groups and Trees
================

As mentioned above, the groups and trees (normal and admin) are just a way to index
things, the names are arbitrary.

Groups can (and should) contain multiple roles. This means that they cannot
easily match the dotted name structure of roles. The RBAC tree reflects functions
that users need to perform, such as "System Administrator", "Club N Directors",
"State N Financial Controllers".

Groups
------

This is the basic structure of the tree and groups for RBAC.

+------------------------+-----------------------------------------+
| Group / Tree           | Purpose                                 |
+========================+=========================================+
| rbac.clubs.STATE.N     | | *Things relating to club N*           |
|                        | | e.g. rbac.clubs.SA.N.directors        |
|                        | | rbac.clubs.NSW.N.finance              |
+------------------------+-----------------------------------------+
| rbac.abf               | | *Things relating to the ABF*          |
|                        | | e.g. rbac.abf.finance                 |
|                        | | rbac.abf.forumadmins                  |
+------------------------+-----------------------------------------+
| rbac.general           | | *General this such as public forums   |
|                        | | e.g. rbac.abf.general.forums          |
+------------------------+-----------------------------------------+

Admin
=====

It is important to realise the difference between admin within a module and
admin for RBAC. For example, if you are in the group *rbac.abf.forumadmins*
this allows you to create and delete forums. However, it doesn't give you any
rights to change the RBAC tree itself. You can't add other users to this
group for example. If you could, then it would be chaos, once one person
got into a group they could let all of their friends in too.

Admin has a separate structure. There are two things required, what you can do,
and where you can do it. The WHAT is which roles you are an admin for. Putting
a user into an admin group for forums should not allow them to also administer
payments. The WHERE is the location the tree that you are an admin for.
Making a club owner an admin for their club in the tree and giving them
admin rights for roles relating to their club (payments for their club,
settings for their club, their club forum etc) should not allow them to do
the same thing for another club.

+------------------------+-------------------------+--------------------------+------------------------------+
| Group / Tree           | Purpose                 | Typical Roles            |  Where in Tree               |
+========================+=========================+==========================+==============================+
| admin.clubs.STATE.N    | *Admin for club N*      | | forums.forum.N         | | rbac.clubs.STATE.N         |
|                        |                         | | org.org.N              | | e.g. rbac.clubs.SA.324     |
|                        |                         |                          | | rbac.clubs.NSW.23          |
+------------------------+-------------------------+--------------------------+------------------------------+
| admin.abf.finance      | *Finance for ABF*       | | payments.global.view   | rbac.abf                     |
|                        |                         | | payments.global.manage |                              |
+------------------------+-------------------------+--------------------------+------------------------------+
| admin.abf.forums       | *Forums management*     | forums.forumadmin        | rbac.abf                     |
|                        |                         |                          |                              |
+------------------------+-------------------------+--------------------------+------------------------------+
| admin.abf.clubs        | *Central club admin*    | | payments.org           | rbac.clubs                   |
|                        |                         | | org.org                |                              |
|                        |                         | | forums.forum           |                              |
+------------------------+-------------------------+--------------------------+------------------------------+


Admin for Admin
===============

Any admin can add another user to a group that they are an administrator for.
Creating new groups will for now be an IT function.
