:orphan:

.. image:: ../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

.. image:: ../images/time.jpg
 :width: 300
 :alt: Time

=====================
Cobalt in Two Minutes
=====================

If you are an experienced Django developer and just want to find out what you need to know
about this project before you get started, this page is for you.

************************
Design
************************

- Vanilla Django application with multiple modules and a Postgres database
- Interfaces with Stripe (for payments) and AWS (for email sending)
- Custom built security sub-system (*See* :doc:`rbac_overview`)
- Heavy backend, light frontend

***************************
Things You May Find Unusual
***************************

- Not built using Django Rest Framework. We use `Django Ninja <https://django-ninja.rest-framework.com/>`_ instead as it is much simpler and meets our needs better.
- Not built with a heavyweight client side framework (*see below for more on the client side*).
- No Celery. Too complicated for this project. We use cron instead.
- No Docker. We don't need it. We deploy on a standardised VM environment and use a virtual environment.
- No Class Based Views. In our opinion it was a mistake adding these to Django and they should be avoided. `This explains it well <https://lukeplant.me.uk/blog/posts/djangos-cbvs-were-a-mistake/>`_.
- Custom testing framework (*See* :doc:`testing_overview` and :doc:`test_data_overview`).

******************
Client Side
******************

- `HTMX <https://htmx.org/>`_ is used instead of a client side framework like React or Vue
- `_hyperscript <https://hyperscript.org/>`_ is used for simple DOM activities
- `JQuery <https://jquery.com/>`_ is used for anything more complex
- A `Bootstrap 4 <https://getbootstrap.com/>`_ template was used to start the project

******************
Useful to Know
******************

- Deployed on AWS (*See* :doc:`aws_overview`)
- CGIT scripts (:doc:`utilities_overview`) assist with AWS and GIT integrations (not essential, but highly recommended)
- Limited use of signals or other advanced Django features
- Some use of decorators
- All configuration controlled through environment variables
- Django management commands used for setting up reference data and cron
- Uses Django Post Office and Django SES for email sending
- Aspires to be an international application but has a long way to go
- One piece of middleware - controls shutting down the site for maintenance

********************
Coding Standards etc
********************

- Use the git pre-commits included with the code
- Black is used for opinionated code formatting
- Use HTMX if possible - it is **not** a client side framework, it allows the client side to be controlled by the server side so our *client side* code is really Django.
- Build tests as you go
- Use CGIT for deployment unless you are sure of what you are doing
- The design has changed over time and we don't go back and fix things that work, but if you are doing major work on something old, consider refactoring it at least

