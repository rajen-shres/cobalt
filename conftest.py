# import pytest
#
# from cobalt.settings import set_value
#
# pytestmark = pytest.mark.django_db
#
#
# @pytest.fixture()
# def django_db_setup():
#
#     RDS_DB_NAME = set_value("RDS_DB_NAME")
#     RDS_USERNAME = set_value("RDS_USERNAME")
#     RDS_PASSWORD = set_value("RDS_PASSWORD")
#     RDS_HOSTNAME = set_value("RDS_HOSTNAME")
#     RDS_PORT = set_value("RDS_PORT")
#
#     settings.DATABASES["default"] = {
#         "ENGINE": "django.db.backends.postgresql_psycopg2",
#         "NAME": RDS_DB_NAME,
#         "USER": RDS_USERNAME,
#         "PASSWORD": RDS_PASSWORD,
#         "HOST": RDS_HOSTNAME,
#         "PORT": RDS_PORT,
#     }
#
#
# @pytest.fixture(autouse=True)
# def auto_fixture():
#     """This is automatically loaded every time we run pytest"""
#
#
# def pytest_html_report_title(report):
#     report.title = "your title!"
