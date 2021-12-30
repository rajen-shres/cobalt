"""This is really a unit test but it needs a Django server in order to work so runs as an integration test"""
import json
import time
from base64 import b64encode

import requests
from fcm_django.models import FCMDevice

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

        # Missing parameters
        response = requests.get(self.fcm_url)

        ok = response.status_code == 405

        self.manager.save_results(
            status=ok,
            test_name="Call API without parameters",
            test_description="Call the API without providing parameters, should fail.",
            output=f"status code={response.status_code}. Expected 405.",
        )

        # Invalid data - userid
        data = {
            "username": "Invalid",
            "password": self.manager.test_code,
            "fcm_token": "1234567890",
        }

        response = requests.post(self.fcm_url, json=data)

        self.manager.save_results(
            status=response.status_code == 403,
            test_name="Call FCM Token API with invalid data - userid",
            test_description="Call the API with incorrect data (userid)",
            output=f"status code={response.status_code}. Expected 403.",
        )

        # Invalid data - password
        data = {
            "username": self.manager.alan.system_number,
            "password": "invalid",
            "fcm_token": "1234567890",
        }

        response = requests.post(self.fcm_url, json=data)

        self.manager.save_results(
            status=response.status_code == 403,
            test_name="Call FCM Token API with invalid data - Password",
            test_description="Call the API with incorrect data (password)",
            output=f"status code={response.status_code}. Expected 403.",
        )

        # Valid data - login with system_number
        data = {
            "username": self.manager.alan.system_number,
            "password": self.manager.test_code,
            "fcm_token": "1234567890",
        }

        response = requests.post(self.fcm_url, json=data)

        self.manager.save_results(
            status=response.status_code,
            test_name="Call FCM Token API with valid data. Use system number",
            test_description="Call the API with correct data using system_number",
            output=f"status code={response.status_code}. Expected 200.",
        )

        # Check it worked
        fcm_token = FCMDevice.objects.filter(user=self.manager.alan).last()
        if fcm_token and fcm_token.registration_id == "1234567890":
            ok = True
            token = fcm_token.registration_id
        else:
            ok = False
            token = "FCMDevice object not found"

        self.manager.save_results(
            status=ok,
            test_name="Call FCM Token API with valid data (login with system_number) - check token is saved",
            test_description="Call the API with correct data and check it saves token",
            output=f"Expected token to be '1234567890'. Got '{token}'",
        )

        # Valid data - login with email
        self.manager.alan.email = "fish@chips.com"
        self.manager.alan.save()

        data = {
            "username": "fish@chips.com",
            "password": self.manager.test_code,
            "fcm_token": "123456789044",
        }

        response = requests.post(self.fcm_url, json=data)

        self.manager.save_results(
            status=response.status_code,
            test_name="Call FCM Token API with valid data. Use email",
            test_description="Call the API with correct data using email",
            output=f"status code={response.status_code}. Expected 200.",
        )

        # Check it worked
        fcm_token = FCMDevice.objects.filter(user=self.manager.alan).last()
        if fcm_token and fcm_token.registration_id == "123456789044":
            ok = True
            token = fcm_token.registration_id
        else:
            ok = False
            token = "FCMDevice object not found"

        self.manager.save_results(
            status=ok,
            test_name="Call FCM Token API with valid data (login with email) - check token is saved",
            test_description="Call the API with correct data and check it saves token",
            output=f"Expected token to be '123456789044'. Got '{token}'",
        )
