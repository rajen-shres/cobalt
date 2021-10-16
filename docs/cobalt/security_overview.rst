:orphan:

.. image:: ../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

.. image:: ../images/security.jpg
 :width: 300
 :alt: Security

Security Overview
=================

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