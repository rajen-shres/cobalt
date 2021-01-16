""" Cobalt Settings.py
    ------------------

This is the single settings.py for all Cobalt environments.

We manage all configuration differences through environment variables.
This provides security for confidential information in the online
environments (Test, UAT and Production) which is managed by Elastic
Beanstalk through settings which become environment at run-time.

For development you also need to set environment variables or it
won't work.

readthedocs somehow runs the code as well in order to generate the
documentation and this requires variables to be defined, so as well as importing
the variables from the environment, we also have to define them (with dummy
values) within this file.

"""

import os
import ast
from django.contrib.messages import constants as messages

###########################################
# function to set values from environment #
# variables.                              #
###########################################


def set_value(val_name, default="not-set"):
    if val_name in os.environ:
        return os.environ[val_name]
    else:
        return default


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
DEBUG = set_value("DEBUG", False)

# Set up ADMINS list from string
ADMINS = [
    ("Mark Guthrie", "m@rkguthrie.com"),
    ("Julian Foster", "julianrfoster@gmail.com"),
]

# Fix later
# admin_string = set_value("ADMINS", '("Mark Guthrie", "m@rkguthrie.com")')
# print("admin_string: " + admin_string)
# ADMINS = list(ast.literal_eval(admin_string))
# print(ADMINS[0])

SERVER_EMAIL = set_value("SERVER_EMAIL", "notset@myabf.com.au")

# masterpoints server
GLOBAL_MPSERVER = set_value("GLOBAL_MPSERVER")

# email
EMAIL_HOST = set_value("EMAIL_HOST")
EMAIL_HOST_USER = set_value("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = set_value("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = set_value("DEFAULT_FROM_EMAIL", "notset@fake.com")
# TODO: SUPPORT_EMAIL is only used to send client side errors - replace with ADMINS
SUPPORT_EMAIL = set_value("SUPPORT_EMAIL", ["m@rkguthrie.com"])

# stripe
STRIPE_SECRET_KEY = set_value("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = set_value("STRIPE_PUBLISHABLE_KEY")

# aws
AWS_ACCESS_KEY_ID = set_value("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = set_value("AWS_SECRET_ACCESS_KEY")

# our logical hostname (dev, test, uat, prod)
COBALT_HOSTNAME = set_value("COBALT_HOSTNAME", "127.0.0.1:8000")

# Hostname set by AWS
HOSTNAME = set_value("HOSTNAME", "Unknown")

# database
RDS_DB_NAME = set_value("RDS_DB_NAME")
RDS_USERNAME = set_value("RDS_USERNAME")
RDS_PASSWORD = set_value("RDS_PASSWORD")
RDS_HOSTNAME = set_value("RDS_HOSTNAME")
RDS_PORT = set_value("RDS_PORT")
USE_SQLITE = set_value("USE_SQLITE", 0)

if USE_SQLITE == "True":
    print("Using SQLite")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR + "/db.sqlite3",
        }
    }

else:

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

#########################################
# Dynamic settings.                     #
#########################################
ALLOWED_HOSTS = [
    ".abftech.com.au",
    "myabf.com.au",
    ".myabf.com.au",
    "127.0.0.1",
    "bs-local.com",
    "localhost",
    ".eba-4ngvp62w.ap-southeast-2.elasticbeanstalk.com",
]

# For AWS we also need to add the local IP address as this is used by the health checks
# We do this dynamically
# Windows doesn't support this and isn't used on AWS so skip unless Unix
if os.name == "posix":
    local_ip = os.popen("hostname -I 2>/dev/null").read()
    ALLOWED_HOSTS.append(local_ip.strip())

#########################################
# Common settings for all environments  #
#########################################
AWS_REGION_NAME = "ap-southeast-2"

INSTALLED_APPS = [
    "calendar_app",
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
    "utils",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django_summernote",
    "crispy_forms",
    # "health_check",
    # "health_check.db",
    # "health_check.cache",
    # "health_check.storage",
    "widget_tweaks",
    "django_extensions",
    "django.contrib.admindocs",
]

MIDDLEWARE = [
    "utils.middleware.CobaltMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    #    "django.middleware.common.BrokenLinkEmailsMiddleware",
]

ROOT_URLCONF = "cobalt.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": ["cobalt/templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "cobalt.context_processors.global_settings",
            ],
        },
    },
]

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

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
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

# app specific static lives in app_name/static/app_name
# general static lives in STATICFILES_DIRS
# STATICFILES_DIRS = [os.path.join(BASE_DIR, "cobalt/static/")]

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

EMAIL_SUBJECT_PREFIX = "[%s] " % COBALT_HOSTNAME

GLOBAL_ORG = "ABF"
GLOBAL_TITLE = "My ABF"
GLOBAL_CONTACT = "https://abf.com.au/contact"
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
        "airMode": False,
        "width": "100%",
        "height": "600",
        "lang": None,
        "spellCheck": True,
        "toolbar": [
            ["style", ["style"]],
            ["font", ["bold", "italic", "underline"]],
            ["fontname", ["fontname"]],
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
    "attachment_absolute_uri": False,
    "attachment_filesize_limit": 20000000,
}

# Default user to be the everyone user for RBAC
RBAC_EVERYONE = 1

# TBA User for Event entries
TBA_PLAYER = 2

# Org id for the system account
GLOBAL_ORG_ID = 1

# LOGGING = {
#     'version': 1,
#     'disable_existing_loggers': False,
#     'formatters': {
#         'verbose': {
#             'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
#             'style': '{',
#         },
#         'simple': {
#             'format': '{levelname} {message}',
#             'style': '{',
#         },
#     },
#
#     'handlers': {
#         'console': {
#             'level': 'INFO',
#             'class': 'logging.StreamHandler',
#             'formatter': 'simple'
#         },
#         'mail_admins': {
#             'level': 'ERROR',
#             'class': 'django.utils.log.AdminEmailHandler',
#
#         }
#     },
#     'loggers': {
#         'django': {
#             'handlers': ['console'],
#             'propagate': True,
#         },
#         'django.request': {
#             'handlers': ['mail_admins'],
#             'level': 'ERROR',
#             'propagate': False,
#         },
#     }
# }

# ADDITIONAL_LOGGING = {
#     'version': 1,
#     'disable_existing_loggers': False,
#     'handlers': {
#         'console': {
#             'class': 'logging.StreamHandler',
#         },
#     },
#     'loggers': {
#         # The 'django' logger is the catch-all logger for messages in the Django hierarchy
#         # (cf. https://docs.djangoproject.com/en/1.11/topics/logging/#django)
#         'django': {
#             'handlers': ['console','mail_admin'],
#             'level': 'INFO',
#         },
#     },
# }

# logging
# LOGGING = {
#     "version": 1,
#     "disable_existing_loggers": False,
#     "handlers": {
#         "file": {
#             "level": "INFO",
#             "class": "logging.FileHandler",
#             "filename": "/tmp/cobalt.log",
#         },
#     },
#     "loggers": {"django": {"handlers": ["file"], "level": "DEBUG", "propagate": True}},
# }
