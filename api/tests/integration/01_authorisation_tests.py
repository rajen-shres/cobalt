"""This is really a unit test but it needs a Django server in order to work so runs as an integration test"""
from base64 import b64encode

import requests

from accounts.models import APIToken
from tests.test_manager import CobaltTestManagerIntegration

API_VERSION = "v1.0"


class APITests:
    """Core unit tests for the API. These test security mainly, specific functional API tests live elsewhere."""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager

        # Create an API token to use for testing
        self.token = APIToken(user=self.manager.fiona)
        self.token.save()

        # URL needs to be hardcoded, reverse() won't work with Django Ninja
        self.check_url = f"{self.manager.base_url}/api/cobalt/keycheck/{API_VERSION}"

    def a1_api_authentication(self):
        """Test the API"""

        # Not authorised
        response = requests.get(self.check_url)

        ok = response.status_code == 401

        self.manager.save_results(
            status=ok,
            test_name="Call GET API without authentication",
            test_description="Call the API without providing authentication, should fail.",
            output=f"status code={response.status_code}. Expected 401.",
        )

        # Using query key - valid
        response = requests.get(f"{self.check_url}?key={self.token.token}")

        self.manager.save_results(
            status=response.status_code,
            test_name="Call GET API with query key authentication",
            test_description="Call the API with correct key in query key.",
            output=f"status code={response.status_code}. Expected 200.",
        )

        # Using query key - invalid
        response = requests.get(f"{self.check_url}?key=some_rubbish")

        ok = response.status_code == 401

        self.manager.save_results(
            status=ok,
            test_name="Call GET API with query key authentication, incorrect key",
            test_description="Call the API with incorrect key in query key.",
            output=f"status code={response.status_code}. Expected 401.",
        )

        # Using query key - valid
        response = requests.get(f"{self.check_url}?key={self.token.token}")

        self.manager.save_results(
            status=response.status_code,
            test_name="Call GET API with query key authentication",
            test_description="Call the API with correct key in query key.",
            output=f"status code={response.status_code}. Expected 200.",
        )

        # Using header key - valid
        response = requests.get(self.check_url, headers={"key": self.token.token})

        ok = response.status_code == 200

        self.manager.save_results(
            status=ok,
            test_name="Call GET API with header key authentication, correct key",
            test_description="Call the API with correct key in header.",
            output=f"status code={response.status_code}. Expected 200.",
        )

        # Using header key - invalid
        response = requests.get(self.check_url, headers={"key": "some_rubbish"})

        ok = response.status_code == 401

        self.manager.save_results(
            status=ok,
            test_name="Call GET API with header key authentication, incorrect key",
            test_description="Call the API with correct key in header.",
            output=f"status code={response.status_code}. Expected 401.",
        )

        # Using bearer key - valid
        response = requests.get(
            self.check_url, headers={"Authorization": f"Bearer {self.token.token}"}
        )

        ok = response.status_code == 200

        self.manager.save_results(
            status=ok,
            test_name="Call GET API with bearer key authentication, correct key",
            test_description="Call the API with correct key in header bearer.",
            output=f"status code={response.status_code}. Expected 200.",
        )

        # Using bearer key - invalid
        response = requests.get(
            self.check_url, headers={"Authorization": "Bearer some_rubbish"}
        )

        ok = response.status_code == 401

        self.manager.save_results(
            status=ok,
            test_name="Call GET API with bearer key authentication, incorrect key",
            test_description="Call the API with incorrect key in header bearer.",
            output=f"status code={response.status_code}. Expected 401.",
        )
