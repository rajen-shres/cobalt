:orphan:

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

#######################
Email Overview
#######################

Introduction
============

We got a to a point with Cobalt where basic email wasn’t enough. We had a few attempts to make it more
robust with cron jobs to catch unset emails etc, but fundamentally it needed an overhaul.
For email campaigns we had the choice of using a third party application such as MailChimp or
building the functionality we needed into Cobalt. We went for the latter, partly due to the high
cost of email platforms but also as the work to build it into Cobalt was likely to be similar
to the integration effort, and the user experience should be a lot better and more tightly
integrated than using two systems for fundamentally the same function.

The goal was to get reliable bulk email (up to 50,000 to more than cater for the user base),
as well as to get proper tracking of bounces, deliveries and reads.

For the ABF version of Cobalt we are basically tied into Amazon SES
(https://aws.amazon.com/ses/) at least for the time being.

We use two packages to help us with this:

* **Django Post-Office** (https://pypi.org/project/django-post-office/) installs as a replacement email backend and handles secure delivery and bulk emails. It actually uses any other email backend to do the sending so you can use this without relying on AWS SES.
* **Django SES** (https://github.com/django-ses/django-ses) is a replacement email backend that tightly integrates with SES. You can send emails using SES simply through SMTP but Django SES uses BOTO3 which is more efficient and can receive status updates back from SES.

Environments
============

While there is no such thing as a non-production email account, we are able to separate the
SES infrastructure for each environment (Test, UAT and Production). Testing of return messages
from SES is not possible in Development. To do any significant work in Development it is
recommended that you run up a temporary server on the Internet to use as a development machine.

Things to Watch Out For
=======================

Django SES comes with the ability to check that the certificate is valid when we receive
a call from AWS SES. This is the default behaviour and requires m2crypto to be installed.
For Python 3 you can't easily install m2crypto using pip and the work around is to install
it into the OS. The package is old and the install is fiddly. We decided that it was less
risk not to check the certificate than to open ourselves to problems with newer OS versions
that would stop the whole of Cobalt from installing. It would be possible for someone to
fake an email being opened but the impact of that is very small.

To disable the need for m2crypto we set::

    AWS_SES_VERIFY_EVENT_SIGNATURES = False

In order to successful receive signals from Django SES when DEBUG is False, we need to call::

    func_accepts_kwargs()

This is strange as it shouldn't actually change anything. Check the code
in :func:`notifications.apps.NotificationsConfig` for more details.



