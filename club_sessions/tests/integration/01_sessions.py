import shutil
import time

import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from club_sessions.models import Session
from cobalt.settings import MEDIA_ROOT
from tests.test_manager import CobaltTestManagerIntegration

TEST_FILE_PATH = "club_sessions/tests/test_files"
TEST_FILE_OVERWRITE = "club_sessions_tests.csv"

# Payments Bridge Club
CLUB_ID = 13


def _import_session_file(manager, file):
    """Helper to upload a session file. User needs to be logged in."""

    url = manager.base_url + reverse("club_sessions:session_import_file_upload_htmx")

    manager.login_user(manager.alan)
    with open(file) as session_file:
        data = {
            "club_id": CLUB_ID,
            "compscore3": "1",
            "file": session_file,
        }

        manager.client.post(url, data)


class Sessions:
    """Tests for club sessions"""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager

    def a1_simple_session(self):
        # Log in Alan who is an admin for Payments Bridge Club
        self.manager.login_user(self.manager.alan)

        # Import file
        _import_session_file(self.manager, "club_sessions/tests/test_files/basic.csv")

        session_url = self.manager.base_url + reverse(
            "club_sessions:manage_session", kwargs={"session_id": 1}
        )

        # # Connect to page
        self.manager.driver.get(session_url)

        self.manager.sleep()

        self.manager.save_results(
            status=True,
            test_name="Load valid session file",
            output="Loaded a valid session file. Successful.",
            test_description="We load a CS3 format session file and see if it works.",
        )
