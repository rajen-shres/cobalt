import requests
from django.urls import reverse

from accounts.models import APIToken
from tests.test_manager import CobaltTestManagerIntegration


class SMSTests:
    """Unit tests for SMS"""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager

        # Create an API token to use for testing
        self.token = APIToken(user=self.manager.fiona)
        self.token.save()

        # URL needs to be hardcoded, reverse() won't work with Django Ninja
        self.sms_url = "http://127.0.0.1:8000/api/cobalt/keycheck/v1.0"

        self.headers = {"Authorization": f"key:{self.token.token}"}

        print(self.headers)

    def sms_api_calls(self):
        """Test the API"""
        response = requests.get(self.sms_url)
        print(response)
        response = requests.get(self.sms_url, headers=self.headers)
        print(response)
