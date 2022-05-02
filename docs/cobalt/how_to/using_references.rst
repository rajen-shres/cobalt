:orphan:

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

==================================
How To Use The Reference Documents
==================================

When you visit the reference pages you will be taken to the usage documentation by default. This is designed
to help you when trying to work with an application from another application. For example, when you need to
make a payment you can view the payments reference page to see how to use the API.

If you are looking for documentation on how to support that application, you can find a link at the top of each
reference page in the note box.

When viewing the usage documentation, you will find some general advice and specific examples. However, you won't
find a lot of description of the parameters or return values. These are documented directly within the code and
you can view them by clicking on the link above each example. E.g. this is taken from payment:

Get a User's Balance
====================

:func:`payments.payments_views.core.get_balance`

.. code-block::

    from payments.payments_views.core import get_balance

    >>> get_balance(user)
    100.0

To see what parameters are used, what the function has to say about itself and even to view the code directly,
you can click on the link at the top, directly underneath **Get a User's Balance**.