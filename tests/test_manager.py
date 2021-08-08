import importlib
import inspect

from termcolor import colored
from django.template.loader import render_to_string
from django.test import Client
from django.test.utils import setup_test_environment
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions

from accounts.models import User

# Stop sending emails plus some other things we don't care about
setup_test_environment()

# List of tests to run format is "class": "location"
LIST_OF_TESTS = {
    # "Example": "payments.tests.example",
    "MemberTransfer": "payments.tests.member_actions",
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
    3) Selenium - Selenium handles the UI tests. These tests interact with
                  the UI in the same way as a user would and test both the server
                  and client code, although ugly screens and typos will not be
                  detected. This can also test different browsers.

    This class provides basic set up for the tests that are run and collates the
    results.

    To add tests you can copy an existing one. Tests can use any combination of the
    approaches mentioned above.
    """

    def __init__(self, app, browser, base_url, headless):
        """Set up basic environment for individual tests"""

        if not browser:
            browser = "chrome"

        if not base_url:
            base_url = "http://127.0.0.1:8000"

        self.base_url = base_url

        # Specify app to only run specific tests
        self.app_to_test = app

        # Create test client
        self.client = Client()

        # Create Selenium client
        if browser == "chrome":
            options = ChromeOptions()
            if headless:
                options.headless = True
            self.driver = webdriver.Chrome(options=options)

        if browser == "firefox":
            options = FirefoxOptions()
            if headless:
                options.headless = True
            self.driver = webdriver.Firefox(options=options)

        # Default system-wide pwd
        self.test_code = "F1shcake"

        # First user - Alan Admin
        self.test_user = self.get_user("100")

        # Log user in
        self.login_user(self.test_user)

        # Variables for results of tests
        self.overall_success = True
        self.test_results = {}  # actual results
        self.test_results_list = []  # order of results
        self.class_docs = {}  # Doc strings for classes
        self.nice_function_names = {}  # turn function names into nice strings

    def get_user(self, username):
        """Get a user by username"""
        return User.objects.filter(username=username).first()

    def login_user(self, user):
        """Login user to both test client and Pylenium"""
        self.login_test_client(user)
        self.login_selenium_user(user)

    def login_test_client(self, user):
        """login user through test client interface"""
        self.client.force_login(user)

    def login_selenium_user(self, user):
        """login user through browser"""
        self.driver.get(f"{self.base_url}/accounts/login")
        self.driver.find_element(By.ID, "id_username").send_keys(
            self.test_user.username
        )
        self.driver.find_element(By.ID, "id_password").send_keys(self.test_code)
        self.driver.find_element_by_class_name("btn").click()

    def save_results(self, status, test_name, test_description=None, output=None):
        """handle logging results

        args:
            status: Boolean for success or failure OR HTTP Status Code
            test_name: Str. Name of test (short description)
            test_description: Str. Explains what this test does in detail (optional)
            output: Output from test

        """

        # If we got a number for status, convert to True or False from success HTTP codes
        if isinstance(status, str):
            status = status in ["200", "301", "302"]
        if isinstance(status, int):
            status = status in [200, 301, 302]

        # work out who called us
        # - if the level up isn't a class we could be in a common helper functions so try next level
        stack = inspect.stack()
        try:
            calling_class = stack[1][0].f_locals["self"].__class__.__name__
            calling_class_doc = stack[1][0].f_locals["self"].__class__.__doc__
            calling_method = stack[1][0].f_code.co_name
        except KeyError:
            calling_class = stack[2][0].f_locals["self"].__class__.__name__
            calling_class_doc = stack[2][0].f_locals["self"].__class__.__doc__
            calling_method = stack[2][0].f_code.co_name

        # dictionary for class doc strings
        if calling_class not in self.class_docs:
            self.class_docs[calling_class] = calling_class_doc

        # dictionary for nice function names
        if calling_method not in self.nice_function_names:
            self.nice_function_names[calling_method] = calling_method.replace(
                "_", " "
            ).title()

        # create dictionary entries if new

        if calling_class not in self.test_results:
            self.test_results[calling_class] = {}

        if calling_method not in self.test_results[calling_class]:
            self.test_results[calling_class][calling_method] = {}

        self.test_results[calling_class][calling_method][test_name] = {
            "status": status,
            "test_description": test_description,
            "output": output,
        }

        # Add to our list if not already there
        this_id = f"{calling_class}:{calling_method}"
        if this_id not in self.test_results_list:
            self.test_results_list.append(this_id)

        if not status:
            self.overall_success = False
            status_coloured = colored(
                "Fail", "yellow", "on_blue", attrs=["blink", "bold"]
            )
        else:
            status_coloured = colored("Pass", "white", "on_magenta", attrs=["bold"])

        test_name_coloured = colored(test_name, "green")
        calling_method_coloured = colored(calling_method, "cyan")

        print(
            f"[{status_coloured} - {test_name_coloured} in {calling_method_coloured}]"
        )

    def report(self):
        """Report on total test findings"""

        print("\n\n-----------------------------------------\n")

        if self.overall_success:
            print("Success!!!")
        else:
            print("Failed")

        print("\n-----------------------------------------\n")

        for result_item in self.test_results_list:
            calling_class, calling_method = result_item.split(":")

            for test_name in self.test_results[calling_class][calling_method]:
                item = self.test_results[calling_class][calling_method][test_name]
                status = item["status"]
                error_desc = item["output"]
                status_word = "Pass" if status else "Fail"
                print(
                    f"{calling_class} - {calling_method} - {test_name} - {status_word}"
                )
                if not status and error_desc:
                    print(error_desc)

    def report_html(self):
        """return report as html"""

        data = {}

        for result_item in self.test_results_list:
            calling_class, calling_method = result_item.split(":")

            if calling_class not in data:
                data[calling_class] = {}

            if calling_method not in data[calling_class]:
                data[calling_class][calling_method] = []

            length = len(self.test_results[calling_class][calling_method])
            for counter, test_name in enumerate(
                self.test_results[calling_class][calling_method], start=1
            ):
                item = self.test_results[calling_class][calling_method][test_name]
                status = item["status"]
                error_desc = item["output"]
                test_description = item["test_description"]
                status_word = "Pass" if status else "Fail"

                data[calling_class][calling_method].append(
                    {
                        "test_name": test_name,
                        "status": status_word,
                        "test_description": test_description,
                        "error_desc": error_desc,
                        "counter": f"[{counter}/{length}]",
                        "id": f"{calling_method}-{counter}",
                    }
                )
        return render_to_string(
            "tests/basic.html",
            {
                "data": data,
                "class_docs": self.class_docs,
                "nice_function_names": self.nice_function_names,
            },
        )

    def run(self):
        # Actually run the test. Pass in this class instance too.

        # go through list, import and instantiate
        for test_list_item in LIST_OF_TESTS:
            test_class = getattr(
                importlib.import_module(LIST_OF_TESTS[test_list_item]), test_list_item
            )
            class_instance = test_class(self)

            # Check if only running one test
            if (
                self.app_to_test is None
                or self.app_to_test == type(class_instance).__name__
            ):
                print(f"Running {LIST_OF_TESTS[test_list_item]} - {test_list_item}")
                run_methods(class_instance)

        self.driver.quit()
