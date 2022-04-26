import time

from django.urls import reverse

from accounts.models import User
from tests.test_manager import CobaltTestManagerIntegration


class HTMXSearch:
    """Tests for the HTMX Member search. We use a screen within tests for testing it"""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager
        self.manager.login_user(self.manager.alan)

        # Create a user so we have letters in common with Fiona
        self.finn = User(first_name="Finn", last_name="Fredrick", system_number=9999999)
        self.finn.save()

    def a1_test_inline(self):

        # Get url
        url = self.manager.base_url + reverse("tests:htmx_search")

        # Connect to page
        self.manager.driver.get(url)

        # enter name
        self.manager.selenium_wait_for_clickable(
            "id_last_name_searchinline-callback"
        ).send_keys("fr")

        # Should get a match for both
        ff = self.manager.selenium_wait_for_text("Fiona", "name-matchesinline-callback")
        finn = self.manager.selenium_wait_for_text(
            "Finn", "name-matchesinline-callback"
        )

        if ff and finn:
            success = True
        else:
            success = False

        self.manager.save_results(
            status=success,
            test_name="Last Name both match",
            output=f"{success}",
            test_description="Enter 'fr' into last_name field. Expect to match on Fiona and Finn",
        )

        # THIS NEEDS WORK. NEED TO WORK OUT HOW TO FIND ELEMENTS. MATCHES EVEN AFTER THEY HAVE GONE.

        # self.manager.selenium_wait_for_clickable("id_last_name_searchinline-callback").send_keys("ec")
        #
        # # Should get a match for only fiona
        # ff = self.manager.selenium_wait_for_clickable("id_htmx_search_match_inline-callback11")
        # finn = self.manager.selenium_wait_for_clickable("id_htmx_search_match_inline-callback32")
        # finn2 = self.manager.selenium_wait_for_clickable("id_htmx_search_match_inline-callback3222")
        #
        # if ff and not finn:
        #     success = True
        # else:
        #     success = False
        #
        # print(ff)
        # print(finn)
        # print(finn2)
        #
        # self.manager.save_results(
        #     status=success,
        #     test_name="Last Name one match",
        #     output=f"{success}",
        #     test_description="Enter 'frec' into last_name field. Expect to match on Fiona only",
        # )
        #
        # self.manager.sleep()
