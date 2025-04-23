""" Cobalt Settings.py

This is the single settings.py for all Cobalt environments.

We manage all configuration differences through environment variables.
This provides security for confidential information in the online
environments (Test, UAT and Production) which is managed by Elastic
Beanstalk through settings which become environment at run-time.

For development, you also need to set environment variables, or it
won't work.

"""

import os
import ast
from django.contrib.messages import constants as messages
from firebase_admin import initialize_app


###########################################
# function to set values from environment #
# variables.                              #
###########################################
def set_value(val_name, default="not-set"):
    return os.environ[val_name] if val_name in os.environ else default


def apply_large_email_batch_config(batch_size):
    """
    Checks whether a large email batch configuration set is both configured
    and applicable to this batch size.
    """
    if AWS_SES_CONFIGURATION_SET_LARGE is None:
        return False
    return batch_size >= EMAIL_LARGE_BATCH_SIZE


def AWS_SES_configuration_set_selector(
    email_message, dkim_domain=None, dkim_key=None, dkim_selector=None, dkim_headers=()
):
    """
    Selects the appropriate Amazon Simple Email System configuration set for an email,
    based on batch size (optionally passed in the email via a custom header X-Myabf-Batch-Size).
    This function is called by the Django-SES package (specified by AWS_SES_CONFIGURATION_SET),
    and only when AWS_SES_CONFIGURATION_SET_DEFAULT is set.
    See https://github.com/django-ses/django-ses#ses-event-monitoring-with-configuration-sets
    and COB-793 for more details.
    """

    if (
        AWS_SES_CONFIGURATION_SET_LARGE is None
        or "X-Myabf-Batch-Size" not in email_message.extra_headers
    ):
        return AWS_SES_CONFIGURATION_SET_DEFAULT

    batch_size = int(email_message.extra_headers["X-Myabf-Batch-Size"])

    if apply_large_email_batch_config(batch_size):
        return AWS_SES_CONFIGURATION_SET_LARGE
    else:
        return AWS_SES_CONFIGURATION_SET_DEFAULT


###########################################
# base settings that need to come first.  #
###########################################
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

###########################################
# Specific settings per environment.      #
# Override through environment variables. #
# Dummy values are required for read the  #
# docs to work.                           #
###########################################
# basics
SECRET_KEY = set_value("SECRET_KEY")
# DEBUG = set_value("DEBUG", False)
DEBUG = os.environ.get("DEBUG", "ON") == "ON"
API_KEY_PREFIX = set_value("API_KEY_PREFIX", "API_")

# Set up ADMINS list from string
ADMINS = [
    ("Developer Name", "success@simulator.amazonses.com"),
    #   ("Julian Foster", "julianrfoster@gmail.com"),
]

# COB-488 - require 2FA for Admin site access (Y or N)
REQUIRE_2FA = set_value("REQUIRE_2FA", "N") == "Y"

SERVER_EMAIL = set_value("SERVER_EMAIL", "notset@myabf.com.au")

# masterpoints server
GLOBAL_MPSERVER = set_value("GLOBAL_MPSERVER")

# email
EMAIL_HOST = set_value("EMAIL_HOST")
EMAIL_HOST_USER = set_value("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = set_value("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = set_value("DEFAULT_FROM_EMAIL", "notset@fake.com")
# TODO: SUPPORT_EMAIL is only used to send client side errors - replace with ADMINS
SUPPORT_EMAIL = set_value("SUPPORT_EMAIL", ["success@simulator.amazonses.com"])

# playpen - don't send emails from non-prod systems
DISABLE_PLAYPEN = set_value("DISABLE_PLAYPEN", "OFF")

# stripe
STRIPE_SECRET_KEY = set_value("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = set_value("STRIPE_PUBLISHABLE_KEY")

# aws
AWS_ACCESS_KEY_ID = set_value("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = set_value("AWS_SECRET_ACCESS_KEY")
AWS_REGION_NAME = set_value("AWS_REGION_NAME")
AWS_SES_REGION_NAME = AWS_REGION_NAME
AWS_SES_REGION_ENDPOINT = set_value("AWS_SES_REGION_ENDPOINT")

# See COB-793: changes to SES configuration set handling
# Selector function returns the appropriate configuration set for an email
# Either AWS_SES_CONFIGURATION_SET_DEFAULT or AWS_SES_CONFIGURATION_SET must be set
EMAIL_LARGE_BATCH_SIZE = int(set_value("EMAIL_LARGE_BATCH_SIZE", 100))
AWS_SES_CONFIGURATION_SET_DEFAULT = set_value("AWS_SES_CONFIGURATION_SET_DEFAULT", None)
AWS_SES_CONFIGURATION_SET_LARGE = set_value("AWS_SES_CONFIGURATION_SET_LARGE", None)
if AWS_SES_CONFIGURATION_SET_DEFAULT is None:
    AWS_SES_CONFIGURATION_SET = set_value("AWS_SES_CONFIGURATION_SET")
else:
    AWS_SES_CONFIGURATION_SET = AWS_SES_configuration_set_selector

# Set this to false so we don't need to install m2crypto which needs OS installs to work
# Not verifying the certificate is lower risk than having us rely on an OS install
AWS_SES_VERIFY_EVENT_SIGNATURES = False

# our logical hostname (dev, test, uat, prod)
COBALT_HOSTNAME = set_value("COBALT_HOSTNAME", "127.0.0.1:8000")

# Hostname set by AWS
HOSTNAME = set_value("HOSTNAME", "Unknown")

# New Relic App ID - Test, UAT and Prod all have their own IDs. Default to Dev
NEW_RELIC_APP_ID = set_value("NEW_RELIC_APP_ID", "601323710")

# Masterpoint source
MP_USE_FILE = set_value("MP_USE_FILE", None)

# database
RDS_DB_NAME = set_value("RDS_DB_NAME", "cobalt")
RDS_USERNAME = set_value("RDS_USERNAME", "postgres")
RDS_PASSWORD = set_value("RDS_PASSWORD", "postgres")
RDS_HOSTNAME = set_value("RDS_HOSTNAME", "localhost")
RDS_PORT = set_value("RDS_PORT", "5432")
USE_SQLITE = set_value("USE_SQLITE", 0)

# xero
XERO_CLIENT_ID = set_value("XERO_CLIENT_ID")
XERO_CLIENT_SECRET = set_value("XERO_CLIENT_SECRET")
XERO_TENANT_NAME = "17 Ways"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": RDS_DB_NAME,
        "USER": RDS_USERNAME,
        "PASSWORD": RDS_PASSWORD,
        "HOST": RDS_HOSTNAME,
        "PORT": RDS_PORT,
    }
}

# Test Only - Dummy data count
DUMMY_DATA_COUNT = int(set_value("DUMMY_DATA_COUNT", 20))

# Maintenance mode setting used by cobalt.middleware
# Set this to the string "ON" to put site into maintenance mode - only admins can login
MAINTENANCE_MODE = set_value("MAINTENANCE_MODE", "OFF")

# Recaptcha keys
RECAPTCHA_SITE_KEY = set_value("RECAPTCHA_SITE_KEY")
RECAPTCHA_SECRET_KEY = set_value("RECAPTCHA_SECRET_KEY")

#########################################
# Dynamic settings.                     #
#########################################
ALLOWED_HOSTS = [
    "myabf.com.au",
    ".myabf.com.au",
    "127.0.0.1",
    "bs-local.com",
    "localhost",
    "testserver",
    ".eba-4ngvp62w.ap-southeast-2.elasticbeanstalk.com",
]

# In development, allow any connections
if COBALT_HOSTNAME == "127.0.0.1:8000":
    ALLOWED_HOSTS = ["*"]

# For AWS we also need to add the local IP address as this is used by the health checks
# We do this dynamically
# Windows doesn't support this and isn't used on AWS so skip unless Unix
if os.name == "posix":
    local_ip = os.popen("hostname -I 2>/dev/null").read()
    ALLOWED_HOSTS.append(local_ip.strip())

#########################################
# Common settings for all environments  #
#########################################

INSTALLED_APPS = [
    "calendar_app",
    "api",
    "notifications",
    "events",
    "forums",
    "masterpoints",
    "payments",
    "support",
    "accounts",
    "dashboard",
    "results",
    "organisations",
    "logs",
    "rbac",
    "cobalt",
    "club_sessions",
    "utils",
    "tests",
    "xero",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django_summernote",
    "crispy_forms",
    "widget_tweaks",
    "django_extensions",
    "django.contrib.admindocs",
    "post_office",
    "django_ses",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "loginas",
    "fcm_django",
]

MIDDLEWARE = [
    "utils.middleware.CobaltMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "cobalt.middleware.MaintenanceModeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_otp.middleware.OTPMiddleware",
]

ROOT_URLCONF = "cobalt.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": ["cobalt/templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "cobalt.context_processors.global_settings",
                "loginas.context_processors.impersonated_session_status",
            ],
        },
    },
    {
        "BACKEND": "post_office.template.backends.post_office.PostOfficeTemplates",
        "APP_DIRS": True,
        "DIRS": [],
        "OPTIONS": {
            "context_processors": [
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.debug",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.template.context_processors.request",
            ]
        },
    },
]

# We use django-loginas to allow admins to take over sessions
CAN_LOGIN_AS = "utils.can_login_as.check"

CRISPY_TEMPLATE_PACK = "bootstrap4"

WSGI_APPLICATION = "cobalt.wsgi.application"

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = ["accounts.backend.CobaltBackend"]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

EMAIL_BACKEND = "post_office.EmailBackend"

POST_OFFICE = {
    "BACKENDS": {
        "default": "django_ses.SESBackend",
    },
    "TEMPLATE_ENGINE": "post_office",
    "DEFAULT_PRIORITY": "medium",
    "MESSAGE_ID_ENABLED": True,
}


EMAIL_USE_TLS = True
EMAIL_PORT = 587

LANGUAGE_CODE = "en-au"
TIME_ZONE = "Australia/Sydney"
USE_I18N = True
USE_L10N = True
USE_TZ = True
DATE_FORMAT = "j M Y"
TIME_FORMAT = "g:I A"
DATE_INPUT_FORMATS = ["%d %b %Y", "%d/%m/%Y", "%d %b %Y"]
TIME_INPUT_FORMATS = [
    "%I:%M %p",
]

# This is where collectstatic will put the static files it finds
STATIC_ROOT = os.path.join(BASE_DIR, "static")

# External reference point to find static
STATIC_URL = "/static/"

# append MD5 hash to filenames to prevent caching on version change
STATICFILES_STORAGE = "utils.storage.ForgivingManifestStaticFilesStorage"

MEDIA_ROOT = os.path.join(BASE_DIR, "media")
if "FILE_SYSTEM_ID" in os.environ:  # AWS EFS for media
    MEDIA_ROOT = "/cobalt-media"
MEDIA_URL = "/media/"

LOGIN_REDIRECT_URL = "/dashboard"
LOGOUT_REDIRECT_URL = "/"

MESSAGE_TAGS = {
    messages.DEBUG: "alert-info",
    messages.INFO: "alert-info",
    messages.SUCCESS: "alert-success",
    messages.WARNING: "alert-warning",
    messages.ERROR: "alert-danger",
}

EMAIL_SUBJECT_PREFIX = f"[{COBALT_HOSTNAME}] "

GLOBAL_ORG = "ABF"
GLOBAL_TITLE = "My ABF"
GLOBAL_CONTACT = "/support/contact-logged-in"
GLOBAL_ABOUT = "https://abf.com.au"
GLOBAL_COOKIES = "/support/cookies"
GLOBAL_PRODUCTION = "www.myabf.com.au"
GLOBAL_TEST = "test.myabf.com.au"
GLOBAL_PRIVACY = "https://abf.com.au/privacy"
GLOBAL_CURRENCY_SYMBOL = "$"
GLOBAL_CURRENCY_NAME = "Dollar"
BRIDGE_CREDITS = "Bridge Credits"

# Payments auto amounts
AUTO_TOP_UP_LOW_LIMIT = 20
AUTO_TOP_UP_DEFAULT_AMT = 100
AUTO_TOP_UP_MIN_AMT = 50
AUTO_TOP_UP_MAX_AMT = 2000

# django-summernote provides the rich text entry fields

# SUMMERNOTE_THEME = 'bs4'

SUMMERNOTE_CONFIG = {
    "iframe": False,
    "summernote": {
        "fontSizes": ["8", "9", "10", "11", "12", "14", "16", "18", "24", "36"],
        "lineHeights": ["1", "0.5", "0"],
        "airMode": False,
        "width": "100%",
        "height": "600",
        "lang": None,
        "spellCheck": True,
        "toolbar": [
            ["style", ["style"]],
            ["fontsize", ["fontsize"]],
            ["font", ["bold", "italic", "underline"]],
            ["fontname", ["fontname"]],
            ["height", ["height"]],
            ["color", ["color"]],
            ["para", ["ul", "ol", "paragraph"]],
            ["table", ["table"]],
            ["insert", ["link", "picture", "hr"]],
            [
                "cards",
                [
                    "specialcharsspades",
                    "specialcharshearts",
                    "specialcharsdiamonds",
                    "specialcharsclubs",
                    "specialcharshand",
                ],
            ],
            ["view", ["fullscreen", "codeview"]],
            ["help", ["help"]],
        ],
    },
    "attachment_require_authentication": True,
    "disable_attachment": False,
    "attachment_absolute_uri": True,
    "attachment_filesize_limit": 20000000,
}

# COB-947: Removing hard coding of system account ids

# Default user to be the everyone user for RBAC
RBAC_EVERYONE = int(set_value("RBAC_EVERYONE_ID", 1))

# TBA User for Event entries
TBA_PLAYER = int(set_value("TBA_PLAYER_ID", 2))

# ABF User for Announcements
ABF_USER = int(set_value("ABF_USER_ID", 3))

# System accounts
ALL_SYSTEM_ACCOUNTS = [RBAC_EVERYONE, TBA_PLAYER, ABF_USER]
ALL_SYSTEM_ACCOUNT_SYSTEM_NUMBERS = [0, 1, 2]

# ABF Organisation - used for Settlement transactions and other things. Assumed to be the first thing created.
ABF_ORG = 1

# Org id for the system account
GLOBAL_ORG_ID = 1

# Logout users every 100 years or so
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_AGE = 5256000000

# Upgrade to Django 3.2 requires this setting. Not clear if BigAutoField would be better
# This is the current default so using that
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# The bleach module is used to clean user supplied HTML, mainly for textfields from Summernote
BLEACH_ALLOWED_TAGS = [
    "a",
    "abbr",
    "acronym",
    "b",
    "u",
    "blockquote",
    "code",
    "em",
    "i",
    "li",
    "ol",
    "strong",
    "ul",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "br",
    "p",
    "span",
    "font",
    "pre",
    "table",
    "tbody",
    "tr",
    "td",
    "img",
    "hr",
]
BLEACH_ALLOWED_ATTRIBUTES = [
    "title",
    "href",
    "style",
    "color",
    "class",
    "target",
    "src",
    "data-filename",
]
BLEACH_ALLOWED_STYLES = [
    "text-decoration",
    "text-align",
    "line-height",
    "font-size",
    "font-family",
    "background-color",
    "width",
    "float",
]

# Group used to manage the helpdesk staff
RBAC_HELPDESK_GROUP = "rbac.orgs.abf.abf_roles.helpdesk_staff"

# ABF States - org_id, name, state
ABF_STATES = {
    1801: ("BFACT", "ACT"),
    2001: ("NSWBA", "NSW"),
    8901: ("NTBA", "NT"),
    4501: ("QBA", "QLD"),
    5700: ("SABF", "SA"),
    7801: ("TBA", "TAS"),
    3301: ("VBA", "VIC"),
    6751: ("BAWA", "WA"),
}

# On Elastic Beanstalk the userid that we run under seems to change. Set all permissions to 777 as there is
# no sensitive information stored here, and only Django can access the files directly.
FILE_UPLOAD_PERMISSIONS = 0o777
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o777

# Check for default value of COBALT_HOSTNAME. If this is not set to something else then we could be on Read The Docs
# Read the Docs will fail writing to the log file
if COBALT_HOSTNAME == "127.0.0.1:8000":
    LOGFILE = "/tmp/cobalt.log"
else:
    LOGFILE = "/var/log/cobalt.log"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "cobalt": {
            "format": "[%(levelname)-8s] %(asctime)s [%(module)s %(funcName)s %(lineno)d] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "cobalt",
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": LOGFILE,
            "formatter": "cobalt",
        },
    },
    "loggers": {
        "cobalt": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
        },
        "post_office": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
        },
    },
}

GOOGLE_APPLICATION_CREDENTIALS = set_value("GOOGLE_APPLICATION_CREDENTIALS", "NOTSET")
FIREBASE_APP = initialize_app()

# Check if we want to enable the debug toolbar
DEBUG_TOOLBAR_ENABLED = set_value("DEBUG_TOOLBAR_ENABLED", False)
if DEBUG and DEBUG_TOOLBAR_ENABLED:
    INSTALLED_APPS.append("debug_toolbar")
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
    INTERNAL_IPS = [
        "127.0.0.1",
    ]
