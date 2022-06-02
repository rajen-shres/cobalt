:orphan:

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

.. image:: ../../images/snippet.jpg
 :width: 300
 :alt: Environment Variables

#####################
Environment Variables
#####################

Configuration for Cobalt is managed through environment variables. This is the recommended way to manage
applications deployed on AWS Elastic Beanstalk and is also recommended by
`12 Factor <https://12factor.net/config>`_.

Environment variables are loaded into Django through
``cobalt/settings.py`` which handles three kinds of variables for the application:

System Constants
    Things that are fixed across Cobalt

Dynamic Variables
    Things that are worked out at runtime, e.g. ``ALLOWED_HOSTS``

Per-Environment Variables
    Things that change for each runtime environment (Production, UAT, Test, Development),
    e.g. the database parameters. These are the things covered here.

=============================   ===========     ======================================================================================
Variable Name                   Type            Purpose
=============================   ===========     ======================================================================================
SECRET_KEY                      str             Django secret key, must be kept confidential
DEBUG                           bool            Show debug info. Must be False for production
SERVER_EMAIL                    str             From email address. Can be replaced with **DEFAULT_FROM_EMAIL**
GLOBAL_MPSERVER                 str             URL of the Masterpoints server connector
MP_USE_FILE                     bool            If True then we use a local file, not the Masterpoints server
EMAIL_HOST                      str             *No longer required*
EMAIL_HOST_USER                 str             *No longer required*
EMAIL_HOST_PASSWORD             str             *No longer required*
DEFAULT_FROM_EMAIL              str             From email address
SUPPORT_EMAIL                   str             Used to send client side emails. Can be replaced.
DISABLE_PLAYPEN                 str             If set then emails to real users are allowed to be sent. Default is Playpen is on.
STRIPE_SECRET_KEY               str             Stripe credentials. Used by Payments.
STRIPE_PUBLISHABLE_KEY          str             Stripe credentials. Used by Payments.
AWS_ACCESS_KEY_ID               str             AWS credentials. Used for SES and SNS.
AWS_SECRET_ACCESS_KEY           str             AWS credentials. Used for SES and SNS.
AWS_REGION_NAME                 str             AWS geographical location.
AWS_SES_REGION_ENDPOINT         str             AWS SES connection point.
AWS_SES_CONFIGURATION_SET       str             AWS SES connection name.
NEW_RELIC_APP_ID                str             Used by the New Relic browser include to send to New Relic. Account ID etc should also be environment variables but currently aren't.
COBALT_HOSTNAME                 str             Environment name. e.g. Production, UAT, Test
HOSTNAME                        str             Actual server hostname
RDS_DB_NAME                     str             Database name
RDS_USERNAME                    str             Database username
RDS_PASSWORD                    str             Database password
RDS_HOSTNAME                    str             Database host
RDS_PORT                        str             Database port
MAINTENANCE_MODE                str             If "ON" then prevents user connections to Cobalt
RECAPTCHA_SITE_KEY              str             Recaptcha credentials. Used by logged out contact form
RECAPTCHA_SECRET_KEY            str             Recaptcha credentials. Used by logged out contact form
=============================   ===========     ======================================================================================

Not all environment variables are required for Cobalt to work.

You may want to set additional environment variables for development. e.g. ``PYTHONBREAKPOINT`` and
``DUMMY_DATA_COUNT`` which controls how much dummy data to build when running the test scripts.

Development example::

    # Development
    export PYTHONBREAKPOINT=ipdb.set_trace
    export DEBUG=True
    export DUMMY_DATA_COUNT=200

    # Postgres - use your own settings
    export RDS_DB_NAME=ebdb
    export RDS_HOSTNAME=127.0.0.1
    export RDS_PORT=5432
    export RDS_USERNAME=cobalt
    export RDS_PASSWORD=password

    # Masterpoints server - not essential
    export GLOBAL_MPSERVER=http://localhost:8081

    # Email - you can use the email server settings from AWS if you want
    export EMAIL_HOST=smtp.something.com
    export EMAIL_HOST_USER=userid
    export EMAIL_HOST_PASSWORD=password
    export DEFAULT_FROM_EMAIL=donotreply@something.com

    # Stripe - for payments. Set up a free Stripe account
    export STRIPE_SECRET_KEY=sk_test_key
    export STRIPE_PUBLISHABLE_KEY=pk_test_key

    # AWS - for SMS and SES
    export AWS_ACCESS_KEY_ID=SOMETHING
    export AWS_SECRET_ACCESS_KEY=KEY
    export AWS_REGION_NAME=ap-southeast-2
    export AWS_SES_REGION_ENDPOINT=email.ap-southeast-2.amazonaws.com
    export AWS_SES_CONFIGURATION_SET=cobalt-dev
    export SERVER_MAIL='ABF Dev - Errors<m@rkguthrie.com>'

    # Google recaptcha
    export RECAPTCHA_SITE_KEY=<your key>
    export RECAPTCHA_SECRET_KEY=<your secret key>
