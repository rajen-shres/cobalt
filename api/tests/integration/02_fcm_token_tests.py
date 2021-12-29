"""This is really a unit test but it needs a Django server in order to work so runs as an integration test"""
from base64 import b64encode

import requests

from accounts.models import APIToken
from tests.test_manager import CobaltTestManagerIntegration

API_VERSION = "v1.0"


class FCMTokenAPITests:
    """Test the Google Firebase Cloud Messaging (FCM) token API from a mobile client. This API is used
    to add a token to the database for a user when they first set up the mobile app"""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager

        # URL needs to be hardcoded, reverse() won't work with Django Ninja
        self.fcm_url = (
            f"{self.manager.base_url}/api/cobalt/mobile-client-register/{API_VERSION}"
        )

    def a1_api_tests(self):
        """Test the API"""

        # # Missing parameters
        # response = requests.get(self.fcm_url)
        #
        # ok = response.status_code == 401
        #
        # self.manager.save_results(
        #     status=ok,
        #     test_name="Call GET API without authentication",
        #     test_description="Call the API without providing authentication, should fail.",
        #     output=f"status code={response.status_code}. Expected 401.",
        # )

        # Use query key for testing
        response = requests.get(
            f"{self.fcm_url}?username={self.manager.alan.system_number}&password={self.manager.test_code}&fcm_token=1234567890"
        )

        self.manager.save_results(
            status=response.status_code,
            test_name="Call FCM Token API with valid data",
            test_description="Call the API with correct data",
            output=f"status code={response.status_code}. Expected 200.",
        )
