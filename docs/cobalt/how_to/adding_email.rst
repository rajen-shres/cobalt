:orphan:

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

==================================
Adding Email to Cobalt
==================================

For the ABF deployment, we use AWS Simple Email Service (SES). This has callbacks so
we know when an email is delivered and opened. This doesn't work in development, as you
need an internet facing web server to receive the callback.

Using AWS SES
=============

To use Cobalt with AWS SES, first set up your AWS account and enable SES.
For complete instructions see :doc:`../tutorials/aws_overview`.

All you need in order to use SES for emails is to set the appropriate environment
variables::

    EMAIL_HOST=email-smtp.ap-southeast-2.amazonaws.com
    EMAIL_HOST_PASSWORD=somepassword
    EMAIL_HOST_USER=someuser

    # next lines not needed for development
    AWS_SES_REGION_ENDPOINT=email.ap-southeast-2.amazonaws.com
    AWS_SES_CONFIGURATION_SET = set_value("AWS_SES_CONFIGURATION_SET")
    AWS_REGION_NAME=yourregion
    AWS_SES_REGION_ENDPOINT=endpoint

    # Additionally, set the default email to an email address in your domain
    DEFAULT_FROM_EMAIL=ABF Dev<dev@myabf.com.au>

Using Another Email Provider
============================

To use another provider you need to set the EMAIL_HOST, EMAIL_HOST_USER and EMAIL_HOST_PASSWORD
environment variable.

You will also need to direct Django Post Office to use your email backend instead of Django SES.

Change this section of cobalt/settings.py to an appropriate value::

    POST_OFFICE = {
        "BACKENDS": {
            "default": "django_ses.SESBackend",
        },
    ...
    }