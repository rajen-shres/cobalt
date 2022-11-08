:orphan:

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

=========================================
Supporting the Organisations Application
=========================================

*This page describes the internal workings of this application and is intended to
help you if you need to support the code.*


Organisations is highly structured, there are many directory levels which hopefully make
the code easier to navigate.

A small amount of the code is for basic things relating to organisations, but the majority
of the code is for club menus.

RBAC is used extensively within the club menus to control not only access to things,
but whether they are shown
to users in the first place. A decorator does a lot of the access control work.

.. code-block:: python

    @check_club_menu_access()
    def congress_list_htmx(request, club):

The decorator will provide an extra parameter `club` which is the Club object for this organisation.
It gets this from the POST request which comes from HTMX. Additionally, you can supply arguments to
the decorator for it to perform more specific access checks.


For example, in the template::

    <button class="btn bg-primary btn-block"
    id="t_member_add_individual_member"
    hx-post="{% url "organisations:club_menu_tab_members_add_any_member_htmx" %}"
    hx-target="#id_member_add_tab"
    hx-vars="club_id:{{ club.id }}"
    >Add Member</button>

And then in the view, we can check that this user has RBAC access to manage members as well
as just general RBAC access to the club::

    @check_club_menu_access(check_members=True)
    def add_any_member_htmx(request, club):

See the code for the decorator to see what options are supported.
:func:`~organisations.decorators.check_club_menu_access`