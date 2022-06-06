"""This is really a unit test but it needs a Django server in order to work so runs as an integration test"""
import json
import time
from base64 import b64encode

import requests
from fcm_django.models import FCMDevice

from accounts.models import APIToken
from notifications.models import RealtimeNotification
from tests.test_manager import CobaltTestManagerIntegration

API_VERSION = "v1.0"


class FCMAPITests:
    """Not strictly FCM but mostly. These tests are for the mobile clients more advanced features. We don't
    test the mobile client, just the Django APIs that it calls."""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager

        # URL needs to be hardcoded, reverse() won't work with Django Ninja
        self.api_url = (
            f"{self.manager.base_url}/api/cobalt/mobile-client-register/{API_VERSION}"
        )

        # Create a token
        self.fcm_token_betty = FCMDevice(
            user=self.manager.betty, registration_id="I-AM-BETTY"
        )
        self.fcm_token_betty.save()

    def a1_get_unread_messages(self):
        url = f"{self.manager.base_url}/api/cobalt/mobile-client-get-unread-messages/{API_VERSION}"

        # Create some messages
        RealtimeNotification(
            member=self.manager.betty,
            admin=self.manager.alan,
            msg="First Message for Betty",
        ).save()
        RealtimeNotification(
            member=self.manager.betty,
            admin=self.manager.alan,
            msg="Second Message for Betty",
        ).save()
        RealtimeNotification(
            member=self.manager.betty,
            admin=self.manager.alan,
            msg="Third Message for Betty",
        ).save()

        # Get messages
        data = {"fcm_token": self.fcm_token_betty.registration_id}

        response = requests.post(url, json=data)

        if (
            response.status_code == 200
            and len(response.json()["un_read_messages"]) == 3
        ):
            ok = True
            output = f"status code={response.status_code}. Expected 200. Expected 3 messages. Found 3 messages."
        else:
            ok = False
            output = f"status code={response.status_code}. Expected 200. Expected 3 messages. Found {len(response.json()['un_read_messages'])} messages."

        self.manager.save_results(
            status=ok,
            test_name="Call mobile-client-get-unread-messages for Betty",
            test_description="Call mobile-client-get-unread-messages as Betty and check messages are returned.",
            output=output,
        )

        # Try again. Should get no messages
        response = requests.post(url, json=data)

        if response.status_code == 404:
            ok = True
            output = f"status code={response.status_code}. Expected 404. Expected 0 messages. Found 0 messages."
        else:
            ok = False
            output = f"status code={response.status_code}. Expected 404."

        self.manager.save_results(
            status=ok,
            test_name="Call mobile-client-get-unread-messages for Betty with no unread messages",
            test_description="Call mobile-client-get-unread-messages as Betty and check no messages are returned.",
            output=output,
        )

    def a2_get_latest_messages(self):
        url = f"{self.manager.base_url}/api/cobalt/mobile-client-get-latest-messages/{API_VERSION}"

        # Get messages
        data = {"fcm_token": self.fcm_token_betty.registration_id}

        response = requests.post(url, json=data)

        if (
            response.status_code == 200
            and len(response.json()["un_read_messages"]) == 3
        ):
            ok = True
            output = f"status code={response.status_code}. Expected 200. Expected 3 messages. Found 3 messages."
        else:
            ok = False
            output = f"status code={response.status_code}. Expected 200."

        self.manager.save_results(
            status=ok,
            test_name="Call mobile-client-get-latest-messages for Betty",
            test_description="Call mobile-client-get-latest-messages as Betty and check messages are returned.",
            output=output,
        )

    def a3_delete_specific_message(self):
        url = f"{self.manager.base_url}/api/cobalt/mobile-client-delete-message/{API_VERSION}"

        my_msg = RealtimeNotification(
            member=self.manager.betty,
            admin=self.manager.alan,
            msg="Deletable for Betty",
        )
        my_msg.save()
        not_my_msg = RealtimeNotification(
            member=self.manager.alan,
            admin=self.manager.alan,
            msg="Not Deletable for Betty",
        )
        not_my_msg.save()

        # Delete message for Betty as Betty
        data = {
            "fcm_token": self.fcm_token_betty.registration_id,
            "message_id": my_msg.id,
        }

        response = requests.post(url, json=data)

        still_there = RealtimeNotification.objects.filter(pk=my_msg.id).exists()

        if response.status_code == 200 and not still_there:
            ok = True
            output = "Return code was 200. Message has been deleted."
        else:
            ok = False
            output = f"Expected return code of 200. Got {response.status_code}. Expected no matching message. Found {still_there}"

        self.manager.save_results(
            status=ok,
            test_name="Call mobile-client-delete-message for Betty",
            test_description="Call mobile-client-delete-message as Betty and check message is gone.",
            output=output,
        )

        # Delete message for Alan as Betty
        data = {
            "fcm_token": self.fcm_token_betty.registration_id,
            "message_id": not_my_msg.id,
        }

        response = requests.post(url, json=data)

        still_there = RealtimeNotification.objects.filter(pk=not_my_msg.id).exists()

        if response.status_code == 403 and still_there:
            ok = True
            output = "Return code was 403. Message has not been deleted."
        else:
            ok = False
            output = f"Expected return code of 403. Got {response.status_code}. Expected matching message. Found {still_there}"

        self.manager.save_results(
            status=ok,
            test_name="Call mobile-client-delete-message for Betty but not her message_id",
            test_description="Call mobile-client-delete-message as Betty and check message not deleted.",
            output=output,
        )

        # Delete message that doesn't exist as Betty
        data = {
            "fcm_token": self.fcm_token_betty.registration_id,
            "message_id": 9999999999999,
        }

        response = requests.post(url, json=data)

        self.manager.save_results(
            status=response.status_code == 404,
            test_name="Call mobile-client-delete-message for Betty with invalid id",
            test_description="Call mobile-client-delete-message as Betty and check return code.",
            output=f"Expected status=404. Actual status={response.status_code}",
        )

    def a4_delete_all_messages(self):
        url = f"{self.manager.base_url}/api/cobalt/mobile-client-delete-all-messages/{API_VERSION}"

        data = {
            "fcm_token": self.fcm_token_betty.registration_id,
        }

        response = requests.post(url, json=data)

        still_there = RealtimeNotification.objects.filter(
            member=self.manager.betty
        ).exists()

        if response.status_code == 200 and not still_there:
            ok = True
            output = "Return code was 200. Messages have been deleted."
        else:
            ok = False
            output = f"Expected return code of 200. Got {response.status_code}. Expected no matching message. Found {still_there}"

        self.manager.save_results(
            status=ok,
            test_name="Call mobile-client-delete-all-messages for Betty",
            test_description="Call mobile-client-delete-all-messages as Betty and check message deleted.",
            output=output,
        )

        # Try again now messages are gone

        response = requests.post(url, json=data)

        self.manager.save_results(
            status=response.status_code == 404,
            test_name="Call mobile-client-delete-all-messages for Betty with no messages",
            test_description="Call mobile-client-delete-all-messages as Betty and check return code.",
            output=f"Expected status=404. Actual status={response.status_code}",
        )
