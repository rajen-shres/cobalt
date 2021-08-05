import importlib
import inspect
import os
import time

from django.test import Client
from django.test.utils import setup_test_environment
from pylenium.config import PyleniumConfig
from pylenium.driver import Pylenium

from accounts.models import User

setup_test_environment()

# List of tests to run format is "class": "location"
LIST_OF_TESTS = {
    # "Example": "payments.tests.example",
    "PaymentsTest37": "payments.tests.my_big_payments_test",
}


def run_methods(class_instance):
    """copied from stackoverflow - call all methods on class"""
    attrs = (getattr(class_instance, name) for name in dir(class_instance))
    methods = filter(inspect.ismethod, attrs)
    for method in methods:
        try:
            method()
        except TypeError:
            # Can't handle methods which required arguments
            pass


class CobaltTestManager:
    """
    This orchestrates the automated tests.

    It assumes a fresh database is in place.

    Three types of test can be performed:

    1) Internal - using views and models to update and view the data, checking
                  for core functionality
    2) Client   - using Django's test client we can access the "screens" through
                  an API, interacting with the system through POST and GET. This
                  tests the external interfaces but runs no client side code.
    3) Pylenium - Pylenium is a wrapper for Selenium. These tests interact with
                  the UI in the same way as a user would and test both the server
                  and client code, although ugly screens and typos will not be
                  detected. This can also test different browsers.

    This class provides basic set up for the tests that are run and collates the
    results.

    To add tests you can copy an existing one. Tests can use any combination of the
    approaches mentioned above.
    """

    def __init__(self, app, webdriver, base_url="http://127.0.0.1:8000"):
        """Set up basic environment for individual tests"""

        self.base_url = base_url

        if not webdriver:
            webdriver = "chrome"

        # Specify app to only run specific tests
        self.app_to_test = app

        # Create test client
        self.client = Client()

        # Create Pylenium client
        config = PyleniumConfig()
        config.driver.browser = webdriver
        #  config.driver.options = ["headless"]
        self.py = Pylenium(config)

        # Default system-wide pwd
        self.test_code = "F1shcake"

        # Login first user - Alan Admin
        self.login_user("100")

        # Variables for results of tests
        self.overall_success = True
        self.test_results = {}

    #        self.test_results_index = {}

    def login_user(self, username):
        """Login user to both test client and Pylenium"""
        self.login_test_client(username)
        self.login_pylenium_user(username)

    def login_test_client(self, username):
        """login user through test client interface"""
        test_user = User.objects.filter(username=username).first()
        self.client.force_login(test_user)

    def login_pylenium_user(self, username):
        """login user through browser"""
        self.py.visit(f"{self.base_url}/accounts/login")
        self.py.get("#id_username").type(username)
        self.py.get("#id_password").type(self.test_code)
        self.py.get(".btn").click()

    def results(self, status, test_name, details=None):
        """handle logging results

        args:
            status: Boolean for success or failure OR HTTP Status code
            msg: Str. High level message on what this tests
            details: List. List of specific sub-tests performed.

        """

        # If we got a number for status, convert to True or False from success HTTP codes
        if isinstance(status, str):
            status = status in ["200", "301", "302"]

        stack = inspect.stack()
        calling_class = stack[1][0].f_locals["self"].__class__.__name__
        calling_method = stack[1][0].f_code.co_name

        if calling_class not in self.test_results:
            self.test_results[calling_class] = {}

        if calling_method not in self.test_results[calling_class]:
            self.test_results[calling_class][calling_method] = {}

        self.test_results[calling_class][calling_method][test_name] = (status, details)

        if not status:
            self.overall_success = False

        print(f"{calling_class}.{calling_method} - {status} - {test_name}")

    def report(self):
        """Report on total test findings"""

        print("\n\n-----------------------------------------\n")

        if self.overall_success:
            print("Success!!!")
        else:
            print("Failed")

        print("\n\n-----------------------------------------\n")

        for calling_class in self.test_results:
            print(f"\n+++++{calling_class} in {LIST_OF_TESTS[calling_class]}+++++")

            for calling_method in self.test_results[calling_class]:
                for test_name in self.test_results[calling_class][calling_method]:
                    status, error_desc = self.test_results[calling_class][
                        calling_method
                    ][test_name]
                    status_word = "Pass" if status else "Fail"
                    print(f"{calling_method} - {test_name} - {status_word}")
                    if error_desc:
                        print(error_desc)

    def report_html(self):
        """return report as html"""

        if self.failure:
            count_success = len(self.success)
            count_failure = len(self.failure)
            count_total = count_success + count_failure
            html = f"<h2>Failed {count_failure}/{count_total}</h2>\n"
            for item in self.failure:
                html += f"Failed {item['function']} - {item['msg']}\n"
                if item["details"]:
                    for error in item["details"]:
                        html += f"  {error['status']}: {error['msg']}\n"
        else:
            html = "<h1>Success</h1>"
        return html

    def run(self):
        # Actually run the test. Pass in this class instance too.

        # go through list, import and instantiate
        for test_list_item in LIST_OF_TESTS:
            test_class = getattr(
                importlib.import_module(LIST_OF_TESTS[test_list_item]), test_list_item
            )
            class_instance = test_class(self)

            # Check if only running one test
            print(self.app_to_test)
            if (
                self.app_to_test is None
                or self.app_to_test == type(class_instance).__name__
            ):
                run_methods(class_instance)

    # def run_dashboard(self):
    #     response = self.client.get("/dashboard/")
    #     self.results(response.status_code, "Load Dashboard")
    #
    # def run_dashboard_details(self):
    #     """Go to the dashboard and check basic details are present. Currently only balance can be checked"""
    #     response = self.client.get("/dashboard/")
    #     details = []
    #     passing = True
    #
    #     if response.context["payments"]["balance"] == 400:
    #         detail = {"status": True, "msg": "Bridge Credit balance is correct"}
    #     else:
    #         detail = {
    #             "status": False,
    #             "msg": f"Incorrect Bridge Credit amount - expected 400, got {response.context['payments']['balance']}",
    #         }
    #         passing = False
    #     details.append(detail)
    #
    #     self.results(passing, "Load Dashboard and check details", details)
    #
    # def run_forums(self):
    #     response = self.client.get("/forums/")
    #     self.results(response.status_code, "View main forum page")
    #
    # def run_forums_details(self):
    #     """Go to Forums and check basic details are present."""
    #     response = self.client.get("/forums/")
    #     details = []
    #     passing = True
    #
    #     if response.context["forums"][0]["title"] == "System Announcements":
    #         detail = {"status": True, "msg": "Forum 1 correct"}
    #     else:
    #         detail = {
    #             "status": False,
    #             "msg": f"Forum 1 wrong title. Expected 'System Announcements', got {response.context['forums'][0]['title']}",
    #         }
    #         passing = False
    #     details.append(detail)
    #
    #     self.results(passing, "Load Dashboard and check details", details)
    #
    # def run_member_transfer(self):
    #     """perform a member transfer and check results"""
    #
    #     url = reverse("payments:member_transfer")
    #
    #     betty = User.objects.filter(username="101").first()
    #
    #     form_data = {
    #         "transfer_to": betty,
    #         "amount": 54.45,
    #         "description": "test transfer",
    #     }
    #     form = MemberTransfer(data=form_data)
    #     print("Checking form...")
    #     print(form.is_valid())
    #
    #     form_data = {
    #         "transfer_to": betty.id,
    #         "amount": 54.45,
    #         "description": "test transfer",
    #     }
    #
    #     print("Checking POST...")
    #     response = self.client.post(url, form_data)
    #
    #     print(response)
    #
    #     print("check transactions...")
    #     betty_tran = (
    #         MemberTransaction.objects.filter(member=betty)
    #         .order_by("-created_date")
    #         .first()
    #     )
    #     print(betty_tran.description, betty_tran.amount, betty_tran.other_member)
    #
    #     print("Checking statements...")
    #
    #     url = reverse("payments:statement_admin_view", kwargs={"member_id": betty.id})
    #     response = self.client.get(url)
    #     pprint(response.context["things"])
