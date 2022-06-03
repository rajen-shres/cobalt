:orphan:

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

.. image:: ../../images/security.jpg
 :width: 300
 :alt: Security

=================
Security Overview
=================

Cobalt is an Open Source project which contrary to what you might think, actually makes it more
secure than a proprietary system. Since the code can be read by anyone, there is no false sense
of security around, em... security. The main security defenses are:

- Standard libraries (Django and ``pip`` installed Python modules) which are updates regularly and monitored for vulnerabilities
- `Django <https://www.djangoproject.com/>`_ itself which is a highly secure web framework
- `OWASP <https://owasp.org/>`_ approach to secure development
- Role Base Access Control (:doc:`rbac_overview`) which provides granular authorisation security within Cobalt
- `Bandit <https://pypi.org/project/bandit/>`_ and `Safety <https://pypi.org/project/safety/>`_ are run daily against the main branch of code to identify security exposures
- `Git Guardian <https://www.gitguardian.com/>`_ runs automatically to check requirements.txt for any vulnerabilities
- `Sonarqube <https://www.sonarqube.org/>`_ is run on the build server which checks for a number of things including security

For the ABF deployment of Cobalt on AWS, additional controls are in place:

- Databases are only accessible from application servers, not externally
- Environment variables are used to store credentials which are available at runtime and are not part of the code base
- Data is encrypted at rest using AES-256
- Data is encrypted in transit using TLS 1.2

If the budget is ever available, then external penetration testing would be a good idea. This should include
network and application testing.

There are a few minor weak points in the security of the ABF deployment, but for obvious reasons these are
not discussed here.

******
Django
******

Django has excellent security features but it is still very easy to
slip up and have problems. This document gives some practical guidance
on how to stay safe.

The biggest problem by far is user inputs. Never trust anything that has
come from a user, not even administrators.

.. admonition:: Rule 1 - \|safe in templates

    Only use \|safe if you are sure the content is really safe.

By default, Django's templating engine will escape all content. That means
that if you have mark up such as <i> it will turn that into &lt;i&gt;.
However, a lot of times you want to show the HTML. You can do that with
the template tag \|safe. If you do then you are on your own and need to
make sure that the data really is safe.

.. admonition:: Rule 2 - Use format_html

    Don't use mark_safe within a view for the whole string. Always leave it
    to Django to protect user inputs.

.. code:: python

    # If you have a variable url that you know is safe, and a variable username that has come from a user

    # Don't do this
    return mark_safe(f"<a href='{url}'>{username}</a>")

    # Do this
    return format_html("<a href='{}'>{}</a>", mark_safe(url), username)

.. admonition:: Rule 3 - Use bleach for models.TextField

    Check user inputs when you save them, it is the right point to
    prevent problems.

Summernote inputs map to model.TextField and we want them to have
HTML in them so when we show them we have to use \|safe. When you
save them, make sure they actually are safe by using bleach. Bleach
works on an allowed rather than prohibited basis so you need to make
sure that cobalt/settings has the right strings for bleach.

This is easiest done by overriding the save() function within the
model.

.. code:: python

    class Post(models.Model):
        text = models.TextField()

        def save(self, *args, **kwargs):
            if getattr(self, '_text_changed', True):
                self.text = bleach.clean(self.text, strip=True, tags=BLEACH_ALLOWED_TAGS, attributes=BLEACH_ALLOWED_ATTRIBUTES, styles=BLEACH_ALLOWED_STYLES)
            super(Post, self).save(*args, **kwargs)

Note: It is not just TextFields that need to be validated, it is any
field that will be treated as safe.

************
Django Views
************

All views should check for authorised access, unless they are explicitly intended to be public.

As a minimum the decorator ``@login_required()`` should be used to check that the user is
authenticated.

Also look at :doc:`rbac_overview` which covers how to use Cobalt's built in role based security
system.

One useful decorator is::

    from rbac.decorators import rbac_check_role

    @rbac_check_role("some_app.some_role")
    def my_func(request):

    # Your code

This will check that the user has a specific role (can be a selection) before allowing them
access.

It would be really nice to be able to add more parameters to this to allow more granular
security. This would allow the following boilerplate code::

    role = "events.org.%s.edit" % org.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

To be replaced with a decorator::

    @rbac_check_role_with_details("events.org", "edit", org)

The problem is you don't have the parameter **org** available until you have retrieved it from
somewhere (GET or POST). We could somehow make these standard parameters, for example, have the
decorator look for rbac_model_id in the POST but this is really just making the code more
obscure and harder to support (Explicit is better than Implicit). It only saves two lines of code
and probably adds another line or at least a bunch of characters somewhere else.

Some modules provide their own specific decorators, for example, Organisations::

    from organisations.decorators import check_club_menu_access

    @check_club_menu_access()
    def some_func(request, club):

        print(f"This user can access admin functions for club: {club}, or they wouldn't get here")

*************************
Two Factor Authentication
*************************

2FA is enabled for the Django Admin pages using the package
`django-otp <https://django-otp-official.readthedocs.io/en/stable/>`_.
We have also moved the
Django Admin url away from the default to make it harder for hackers to find it.