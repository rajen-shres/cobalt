.. _aws-overview:


.. image:: images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol


AWS Overview
============

Amazon Web Services (AWS) is not required to use Cobalt, but the ABF version runs on AWS and
this document describes some of the parts of that.

AWS Simple Email Service (SES)
------------------------------

We use SES in order to send emails and to get notifications back about status.

Introduction
^^^^^^^^^^^^

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
* **Django SES** (https://github.com/django-ses/django-ses) is a replacement email backend that tightly integrates with SES. You can send emails using SES simply through SMTP but Django SES has more features.

Environments
^^^^^^^^^^^^

While there is no such thing as a non-production email account, we are able to separate the
SES infrastructure for each environment (Test, UAT and Production). Testing of return messages
from SES is not possible in Development. To do any significant work in Development it is
recommended that you run up a temporary server on the Internet to use as a development machine.

AWS Set Up

You need a basic AWS set up to start with and you need SES enabled. This is already well documented.
If you can get to the point where you can send email from your Cobalt system (or anything else)
using SMTP then that is fine.

Add a Configuration Set

Create Configuration Set - call it what you like e.g. Cobalt

Click on it to edit

Add Destination - Cloudwatch

Now call it Cobalt and select all event types (except Rendering Failure).
Use your own domain for open and click tracking. Don’t add a sub-domain

Set the Value Source Type to “Message Tag” and the Dimension Name to
“ses:configuration-set” and the Default Value to “Cobalt”.

Notifications

Go to the SES main panel and choose your domain.

Expand Notifications and click Edit Configuration

Click on Click here to create a new Amazon SNS topic

Call it cobalt_bounces (same for display name)

Create anther one called cobalt_complaints

Set the SNS Topic Configuration to point to these. Leave Deliveries blank.

Django Set Up

This is already done and in the code, but for completeness:

pip install django-post-office

pip install django-ses

Add post_office to your INSTALLED_APPS

./manage.py migrate

Edit settings.py

EMAIL_BACKEND = 'post_office.EmailBackend'

POST_OFFICE = {
    'BACKENDS': {
        'default': 'django_ses.SESBackend',
    },
    'DEFAULT_PRIORITY': 'now',
}
AWS_SES_REGION_NAME = env('AWS_SES_REGION_NAME', default='us-east-1')
AWS_SES_REGION_ENDPOINT = env('AWS_SES_REGION_ENDPOINT', default='email.us-east-1.amazonaws.com')
AWS_SES_CONFIGURATION_SET = env('AWS_SES_CONFIGURATION_SET', default=None)

AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY where already there but need AmazonSESFullAccess

You should now be able to send emails as normal.

Add a path to notifications URLs for the callback from AWS. See Django SES docs for this (also in the code).

Configure Callback in AWS SES

Create a subscription in SNS (not SES)

On Lightsail - sudo apt-get install libssl-dev swig python3-dev gcc

then m2crypto will pip install

On Test:

yum install openssl-devel