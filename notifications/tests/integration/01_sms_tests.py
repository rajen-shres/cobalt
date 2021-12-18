"""This is really a unit test but it needs a Django server in order to work so runs as an integration test"""
import time

import requests

from accounts.models import APIToken
from rbac.tests.utils import unit_test_rbac_add_role_to_user
from tests.test_manager import CobaltTestManagerIntegration

SMS_VERSION = "v1.0"


class SMSTests:
    """Unit tests for SMS. Only tests failure situations, doesn't actually send any SMS messages."""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager

        # Create an API token to use for testing
        self.token = APIToken(user=self.manager.fiona)
        self.token.save()

        # URL needs to be hardcoded, reverse() won't work with Django Ninja
        self.sms_url = (
            f"{self.manager.base_url}/api/cobalt/sms-file-upload/{SMS_VERSION}"
        )
        self.headers = {"key": self.token.token}

    def a1_sms_api_calls(self):
        """Test the API"""

        # No file provided
        response = requests.post(self.sms_url, headers=self.headers)

        ok = response.status_code == 422

        self.manager.save_results(
            status=ok,
            test_name="Call SMS API without a file",
            test_description="Call the API without providing a file. Should give us a 422 error.",
            output=f"Expected status code of 422. Got {response.status_code}.",
        )

        # User not authorised
        files = {
            "file": open(
                "notifications/tests/integration/test_data/empty_file.txt", "rb"
            )
        }
        response = requests.post(self.sms_url, headers=self.headers, files=files)

        ok = response.status_code == 403

        self.manager.save_results(
            status=ok,
            test_name="Call SMS API - user not authorised",
            test_description="Call the API with a user who doesn't have the right access.",
            output=f"Expected status code of 403. Got {response.status_code}.",
        )

        # Grant access
        unit_test_rbac_add_role_to_user(
            self.manager.fiona, "notifications", "realtime_send", "edit"
        )

        # Empty file
        files = {
            "file": open(
                "notifications/tests/integration/test_data/empty_file.txt", "rb"
            )
        }
        response = requests.post(self.sms_url, headers=self.headers, files=files).json()

        ok = response["status"] == "Failure"

        self.manager.save_results(
            status=ok,
            test_name="Call SMS API with an empty file",
            test_description="Call the API with an empty file.",
            output=f"Expected status = Failure. Got {response['status']}. Response was {response}",
        )

        # Not tab separated row
        files = {
            "file": open(
                "notifications/tests/integration/test_data/missing_tab.txt", "rb"
            )
        }
        response = requests.post(self.sms_url, headers=self.headers, files=files).json()

        ok = response["status"] == "Failure"

        self.manager.save_results(
            status=ok,
            test_name="Call SMS API with no tab character in row",
            test_description="Call the API with a file that is missing tab delimiter.",
            output=f"Expected status = Failure. Got {response['status']}. Response was {response}",
        )

        # Multiple tabs
        files = {
            "file": open(
                "notifications/tests/integration/test_data/multiple_tabs.txt", "rb"
            )
        }
        response = requests.post(self.sms_url, headers=self.headers, files=files).json()

        ok = response["status"] == "Failure"

        self.manager.save_results(
            status=ok,
            test_name="Call SMS API with multiple tab characters in row",
            test_description="Call the API with a file that has multiple tab delimiter.",
            output=f"Expected status = Failure. Got {response['status']}. Response was {response}",
        )

        # No message
        files = {
            "file": open(
                "notifications/tests/integration/test_data/missing_message.txt", "rb"
            )
        }
        response = requests.post(self.sms_url, headers=self.headers, files=files).json()
        ok = response["status"] == "Failure"

        self.manager.save_results(
            status=ok,
            test_name="Call SMS API with missing message",
            test_description="Call the API with a file that has no message.",
            output=f"Expected status = Failure. Got {response['status']}. Response was {response}",
        )

        # Missing ABF Number
        files = {
            "file": open(
                "notifications/tests/integration/test_data/missing_abf_number.txt", "rb"
            )
        }
        response = requests.post(self.sms_url, headers=self.headers, files=files).json()

        ok = response["status"] == "Failure"

        self.manager.save_results(
            status=ok,
            test_name="Call SMS API with an invalid number e.g. string instead of number",
            test_description="Call the API with the number missing.",
            output=f"Expected status = Failure. Got {response['status']}. Response was {response}",
        )

        # Count test
        files = {
            "file": open(
                "notifications/tests/integration/test_data/count_test.txt", "rb"
            )
        }
        response = requests.post(self.sms_url, headers=self.headers, files=files).json()

        ok = response["attempted"] == 5

        self.manager.save_results(
            status=ok,
            test_name="Call SMS API with a mixed file",
            test_description="Call the API with a file that has 5 valid and 7 invalid rows.",
            output=f"Expected status = 5 attempts. Got {response['attempted']}. Response was {response}",
        )
