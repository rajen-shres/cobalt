import logging
import sys
import tempfile
import uuid
import webbrowser

from django.template.loader import render_to_string
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions

logger = logging.getLogger("cobalt")


class SimpleSelenium:
    """high level commands to control selenium. Why this doesn't exist already, I have no idea"""

    def __init__(self, base_url):
        """set up"""

        hello = """
        #######################################
        # Starting
        #######################################
        """
        print(hello)

        self.base_url = base_url
        options = ChromeOptions()
        # options.headless = True
        self.driver = webdriver.Chrome(options=options)
        url = f"{base_url}/accounts/login"

        # Store progress messages
        self.messages = []
        self.screenshots = {}
        self.current_action = "Starting"

        self.add_message(f"Connect to {url}")

        self.driver.get(url)

    def add_message(self, message, link=None):
        self.messages.append(
            {"current_action": self.current_action, "message": message, "link": link}
        )

    def handle_fatal_error(self):
        """we have had a problem - show user and leave"""

        # Save a screenshot
        self.driver.save_screenshot("/tmp/simple_selenium.png")

        # Build HTML page
        html = render_to_string(
            template_name="tests/simple_selenium_fail.html", context={"data": self}
        )

        # Save page
        with open("/tmp/simple_selenium_fail.html", "w") as html_file:
            print(html, file=html_file)

        # Open browser and leave
        webbrowser.open("file:///tmp/simple_selenium_fail.html")
        sys.exit()

    def handle_finish(self):
        """report on how we went"""

        # Build HTML page
        html = render_to_string(
            template_name="tests/simple_selenium_success.html", context={"data": self}
        )

        # Save page
        with open("/tmp/simple_selenium_success.html", "w") as html_file:
            print(html, file=html_file)

        # Open browser
        webbrowser.open("file:///tmp/simple_selenium_success.html")

    def find_by_text(self, search_text):
        """find something with matching text"""

        try:
            match = self.driver.find_element(
                "xpath", f"//*[contains(text(), '{search_text}')]"
            )
        except NoSuchElementException:
            try:
                match = self.driver.find_element(
                    "xpath", f"//input[@value='{search_text}']"
                )
            except NoSuchElementException:
                self.add_message(f"Looked for '{search_text}' but did not find it")
                self.handle_fatal_error()

        self.add_message(f"Looked for '{search_text}' and found it")

        return match

    def press_by_text(self, search_text):
        """find something with matching text and click it"""

        matching_element = self.find_by_text(search_text)
        matching_element.click()
        self.add_message(f"Clicked on '{search_text}'")

    def go_to(self, location):
        """go to a relative path"""
        self.driver.get(f"{self.base_url}{location}")
        self.add_message(f"Went to '{location}'")

    def enter_value_into_field_by_name(self, name, value):
        """find a field by name and put a value in it"""

        try:
            item = self.driver.find_element("name", name)
        except NoSuchElementException:
            self.add_message(f"Couldn't find by name: {name}")
            self.handle_fatal_error()

        self.add_message(f"Found '{name}'")

        item.send_keys(value)

    def screenshot(self, title):
        """grab a picture of the screen"""

        filename = f"/tmp/{uuid.uuid4()}.png"
        self.driver.save_screenshot(filename)
        self.screenshots[filename] = title

        self.add_message(f"Took a screenshot - {title}", link=title)
