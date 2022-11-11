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

For an overview of why email is set up as it is, see  :doc:`../tutorials/aws_overview`.

Pre-requisites
==============

First, set up your basic Cobalt environment on AWS (see :doc:`../tutorials/getting_started`
and :doc:`../tutorials/aws_overview`).

You need a basic AWS set up to start with and you need SES enabled. This is already well documented,
although it is not that straightforward and involves getting permission from Amazon.
If you can get to the point where you can send email from your Cobalt system (or anything else)
using SMTP then that is a fine starting point for this.

.. admonition:: Environments

    While there is no such thing as a non-production email account, we are able to separate the
    SES infrastructure for each environment (Test, UAT and Production). Testing of return messages
    from SES is not possible in Development. To do any significant work in Development it is
    recommended that you run up a temporary server on the Internet to use as a development machine.

Add a Configuration Set
=======================

#. Create a Configuration Set - name it after the environment e.g. cobalt-test
#. Add Destination - SNS
#. Create new SNS Topic - again name it after the environment
#. Select all event types (except Rendering Failure).
#. Use the AWS domain for click and open tracking
#. Now go to SNS and find you topic
#. Add a subscriber and choose HTTPS with the Django URL, e.g. https://test.myabf.com.au/notifications/ses/event-webhook/
#. Django SES will handle the subscription request and this will now be set up
#. Add environment variables for your Cobalt system. You will need: AWS_SES_REGION_NAME, AWS_SES_REGION_ENDPOINT and AWS_SES_CONFIGURATION_SET as well as the AWS credentials.

Environment Variables
=====================

Add environment variables to your environment::

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

To use another provider instead of AWS, you need to set the EMAIL_HOST, EMAIL_HOST_USER and EMAIL_HOST_PASSWORD
environment variable.

You will also need to direct Django Post Office to use your email backend instead of Django SES.

Change this section of cobalt/settings.py to an appropriate value::

    POST_OFFICE = {
        "BACKENDS": {
            "default": "django_ses.SESBackend",
        },
    ...
    }

