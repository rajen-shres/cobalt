import importlib
import inspect
import os

from selenium.common.exceptions import TimeoutException
from termcolor import colored
from django.template.loader import render_to_string
from django.test import Client
from django.test.utils import setup_test_environment
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions

from accounts.models import User

# Stop sending emails plus some other things we don't care about
setup_test_environment()

# List of tests to run format is "class": "location"
LIST_OF_TESTS = {
    #    "MemberTransfer": "payments.tests.member_actions",
    "OrgHighLevelAdmin": "organisations.tests.high_level_admin",
    "ClubLevelAdmin": "organisations.tests.club_level_admin",
    "ClubSettings": "organisations.tests.club_settings",
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

        self.alan = self.get_user("100")
        self.betty = self.get_user("101")
        self.colin = self.get_user("102")
        self.debbie = self.get_user("103")
        self.eric = self.get_user("104")
        self.fiona = self.get_user("105")
        self.gary = self.get_user("106")
        self.heidi = self.get_user("107")
        self.iain = self.get_user("108")
        self.janet = self.get_user("109")
        self.keith = self.get_user("110")

        # First user - Alan Admin
        self.test_user = self.alan

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
        self.driver.find_element(By.ID, "id_username").send_keys(user.username)
        self.driver.find_element(By.ID, "id_password").send_keys(self.test_code)
        self.driver.find_element_by_class_name("btn").click()

    def selenium_wait_for(self, element_id):
        """Wait for element_id to be on page and return it"""
        element_present = expected_conditions.presence_of_element_located(
            (By.ID, element_id)
        )
        WebDriverWait(self.driver, 5).until(element_present)
        return self.driver.find_element_by_id(element_id)

    def selenium_wait_for_clickable(self, element_id):
        """Wait for element_id to be clickable and return it. E.g. if element is hidden."""
        element_clickable = expected_conditions.element_to_be_clickable(
            (By.ID, element_id)
        )
        WebDriverWait(self.driver, 5).until(element_clickable)
        return self.driver.find_element_by_id(element_id)

    def selenium_wait_for_text(self, element_id, text):
        """Wait for text to appear in element_id."""
        element_has_text = expected_conditions.text_to_be_present_in_element(
            (By.ID, element_id), text
        )
        try:
            WebDriverWait(self.driver, 5).until(element_has_text)
            return True
        except TimeoutException:
            return False

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

        # work out who called us
        # - if the level up isn't a class we could be in a common helper functions so try next level
        # - if that fails try another level
        stack = inspect.stack()
        try:
            calling_class = stack[1][0].f_locals["self"].__class__.__name__
            calling_class_doc = stack[1][0].f_locals["self"].__class__.__doc__
            calling_method = stack[1][0].f_code.co_name
            calling_line_no = stack[1][0].f_lineno
            calling_file = stack[1][0].f_code.co_filename
        except KeyError:
            try:
                calling_class = stack[2][0].f_locals["self"].__class__.__name__
                calling_class_doc = stack[2][0].f_locals["self"].__class__.__doc__
                calling_method = stack[2][0].f_code.co_name
                calling_line_no = stack[2][0].f_lineno
                calling_file = stack[2][0].f_code.co_filename
            except KeyError:
                calling_class = stack[3][0].f_locals["self"].__class__.__name__
                calling_class_doc = stack[3][0].f_locals["self"].__class__.__doc__
                calling_method = stack[3][0].f_code.co_name
                calling_line_no = stack[3][0].f_lineno
                calling_file = stack[3][0].f_code.co_filename

        calling_file = os.path.basename(calling_file)

        # dictionary for class doc strings
        if calling_class not in self.class_docs:
            self.class_docs[calling_class] = calling_class_doc.replace("\n", "<br>")

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

        test_name = (
            (test_name[:70] + "..") if len(test_name) > 72 else test_name.ljust(72)
        )
        test_name_coloured = colored(test_name, "green")
        calling_method = (
            (calling_method[:40] + "..")
            if len(calling_method) > 42
            else calling_method.ljust(42)
        )
        calling_method_coloured = colored(calling_method, "cyan")
        calling_line_coloured = (
            colored(calling_file, "green") + ":" + colored(calling_line_no, "green")
        )

        print(
            f"{status_coloured} - {test_name_coloured} in {calling_method_coloured} {calling_line_coloured}"
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
        toc = []
        toc_last_calling_class = None
        total_length = 0
        total_passing = 0

        for result_item in self.test_results_list:
            calling_class, calling_method = result_item.split(":")

            # How many test in this part
            length = len(self.test_results[calling_class][calling_method])

            if calling_class not in data:
                data[calling_class] = {}

            if calling_method not in data[calling_class]:
                data[calling_class][calling_method] = []

                # Table of Contents
                passing = 0
                for test_name in self.test_results[calling_class][calling_method]:
                    if self.test_results[calling_class][calling_method][test_name][
                        "status"
                    ]:
                        passing += 1

                if calling_class != toc_last_calling_class:
                    # New class so show in table
                    display_calling_class = calling_class
                    toc_last_calling_class = calling_class
                else:
                    display_calling_class = None

                toc.append(
                    {
                        "calling_class": display_calling_class,
                        "calling_class_from": LIST_OF_TESTS[calling_class],
                        "calling_method": calling_method,
                        "pass_rate": f"{passing}/{length}",
                    }
                )

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

            total_length += length
            total_passing += passing

            score = total_passing / total_length

            if score == 1.0:
                total_score = "A+"
            elif score > 0.95:
                total_score = "A-"
            elif score > 0.9:
                total_score = "B+"
            elif score > 0.85:
                total_score = "B-"
            elif score > 0.8:
                total_score = "C+"
            elif score > 0.7:
                total_score = "C-"
            elif score > 0.6:
                total_score = "D-"
            else:
                total_score = "Fail"
        return render_to_string(
            "tests/test_results.html",
            {
                "data": data,
                "class_docs": self.class_docs,
                "nice_function_names": self.nice_function_names,
                "toc": toc,
                "total_passing": total_passing,
                "total_length": total_length,
                "total_score": total_score,
            },
        )

    def run(self):
        # Actually run the test. Pass in this class instance too.

        try:

            # go through list, import and instantiate
            for test_list_item in LIST_OF_TESTS:
                test_class = getattr(
                    importlib.import_module(LIST_OF_TESTS[test_list_item]),
                    test_list_item,
                )
                class_instance = test_class(self)

                # Check if only running one test
                if (
                    self.app_to_test is None
                    or self.app_to_test == type(class_instance).__name__
                ):
                    print(
                        f"\nRunning {LIST_OF_TESTS[test_list_item]} - {test_list_item}"
                    )
                    run_methods(class_instance)

            print("\nFinished running tests\n")

        except KeyboardInterrupt:
            print("\nInterrupted\n\n")

        self.driver.quit()
