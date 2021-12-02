import pytest


def pytest_html_report_title(report):
    report.title = "your title!"
