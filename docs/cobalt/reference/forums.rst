:orphan:

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

.. image:: ../../images/forums.jpg
 :width: 300
 :alt: Forums

:doc:`../how_to/using_references`

====================
Forums Application
====================

.. note::
    This page has the documentation on how to use this application
    (externally provided APIs etc). If you are looking for
    information on how it works internally, you can find that in :doc:`./forums_support`.


--------------
Module Purpose
--------------

Account handles things relating to User accounts such as profiles and settings.
There are multiple user types to support the need to deal with users who have not
registered for the system as well as real, registered users.

--------------
External Usage
--------------

Forums handles the general blogging capabilities on Cobalt. This allows
users to communicate with each other, to comment on posts and for clubs
and other organisations to connect with their members and followers.

The codebase for Forums is relatively small and not too hard to understand
by reading the code.

Forums uses RBAC for security. See :doc:`rbac` for more details.
