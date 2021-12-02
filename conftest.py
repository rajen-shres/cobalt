import pytest

from cobalt.settings import set_value
from django.conf import settings


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    """Allow anything to access the database"""
    pass


@pytest.fixture()
def django_db_setup():
    """We build our database outside of pytest, just tell it where to find it"""

    RDS_DB_NAME = set_value("RDS_DB_NAME")
    RDS_USERNAME = set_value("RDS_USERNAME")
    RDS_PASSWORD = set_value("RDS_PASSWORD")
    RDS_HOSTNAME = set_value("RDS_HOSTNAME")
    RDS_PORT = set_value("RDS_PORT")

    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": RDS_DB_NAME,
        "USER": RDS_USERNAME,
        "PASSWORD": RDS_PASSWORD,
        "HOST": RDS_HOSTNAME,
        "PORT": RDS_PORT,
    }


def pytest_html_report_title(report):
    """We use pytest-html to produce a readable report. This sets values for it"""
    report.title = "Cobalt Unit Test Report"
