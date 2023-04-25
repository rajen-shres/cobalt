import logging
import sys
import time
import uuid
import webbrowser

from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from selenium.common.exceptions import NoSuchElementException
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.keys import Keys

logger = logging.getLogger("cobalt")


class SimpleSelenium:
    """high level commands to control selenium. Why this doesn't exist already, I have no idea"""

    def __init__(self, base_url, browser, show, silent):
        """set up"""

        self.base_url = base_url
        self.silent = silent

        options = ChromeOptions()
        if not show:
            options.add_argument("window-size=1200x600")
            options.headless = True

        self.driver = webdriver.Chrome(options=options)
        url = f"{base_url}/accounts/login"

        # Store progress messages
        self.messages = []
        self.screenshots = {}
        self.current_action = "Starting"
        self.title = "Smoke Test"

        self.add_message(f"Connect to {url}")

        self.driver.get(url)

    def add_message(self, message, link=None, bold=False):
        """Add a message to the report on progress"""
        if self.silent:
            return

        if bold:
            message = mark_safe(f"<b>--{message.upper()}--</b>")

        self.messages.append(
            {"current_action": self.current_action, "message": message, "link": link}
        )
        logger.info(message)

    def handle_fatal_error(self):
        """we have had a problem - show user and leave"""

        if self.silent:
            sys.exit(1)

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
        sys.exit(1)

    def handle_finish(self):
        """report on how we went"""

        if self.silent:
            sys.exit(0)

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

    def find_by_name(self, name):
        """find something with matching name"""

        try:
            match = self.driver.find_element("name", name)
        except NoSuchElementException:
            self.add_message(f"Looked for item with name'{name}' but did not find it")
            self.handle_fatal_error()

        self.add_message(f"Looked for item with name '{name}' and found it")

        return match

    def press_by_name(self, name):
        """find something with matching name and click it"""

        matching_element = self.find_by_name(name)
        matching_element.click()
        self.add_message(f"Clicked on '{name}'")

    def go_to(self, location):
        """go to a relative path"""
        self.driver.get(f"{self.base_url}{location}")
        # We don't know if it works, but it should be easy enough to identify if it doesn't
        self.add_message(f"Went to '{location}'")

    def send_enter(self, name):
        """send the enter key to an object"""
        try:
            item = self.driver.find_element("name", name)
        except NoSuchElementException:
            self.add_message(f"Couldn't find by name: {name}")
            self.handle_fatal_error()

        item.send_keys(Keys.RETURN)
        self.add_message(f"Sent enter to '{name}'")

    def enter_value_into_field_by_name(self, name, value):
        """find a field by name and put a value in it. Can be a variable such as password"""

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

        self.add_message(f"Took a screenshot - {title}", link=filename)

    def selectpicker(self, value, name):
        """make bootstrap selectpicker have value specified. NOT FINISHED"""

        # TODO - NOT FINISHED. IT WASN"T A SELECT PICKER

        dropdown = self.driver.find_element("name", name)
        dropdown.click()
        option = self.driver.find_element(
            "css selector",
            f"ul[role=menu] a[data-normalized-text='<span class=\"text\">{value}</span>']",
        )
        option.click()
        # elem.sendKeys("American Samoa");
        # elem.sendKeys(Keys.ENTER);
        self.screenshot("temp")

    def dropdown(self, value, name):
        """choose a value from a dropdown"""

        try:
            self.driver.find_element(
                "xpath", f"//select[@name='{name}']/option[text()='{value}']"
            ).click()
        except NoSuchElementException:
            self.add_message(
                f"Tried to select '{value}' from dropdown '{name}' but couldn't"
            )
            self.handle_fatal_error()

        self.add_message(f"Selected '{value}' from dropdown '{name}'")

    def sleep(self, seconds):
        """sleep for a bit"""
        time.sleep(seconds)
        self.add_message(f"Slept for {seconds} second(s)")

    def set_title(self, title):
        """set the title for the page"""

        self.title = title
