from django.test import Client

from accounts.models import User


class Example:
    def __init__(self, manager):
        self.manager = manager
        # self.client = Client()
        self.client = self.manager.client
        # test_user = User.objects.filter(username='100').first()
        # self.client.force_login(test_user)
        self.py = self.manager.py

    def test_we_can_fill_form(self):
        response = self.manager.client.get("/dashboard/")
        self.manager.results(response.status_code, "Load Dashboard")

        self.py.visit("https://qap.dev")
        self.py.get('a[href="/about"]').hover()
        self.py.get('a[href="/leadership"][class^="Header-nav"]').click()
        if self.py.contains("Carlos Kidman"):
            self.manager.results(True, "Check a website")

    def check_interest_rate_calcs(self):
        print("inside e2x")
        response = self.manager.client.get("/dashboard/")
        self.manager.results(response.status_code, "Perform difficult calcs")

        self.py.visit("https://qap.dev")
        self.py.get('a[href="/about"]').hover()
        self.py.get('a[href="/leadership"][class^="Header-nav"]').click()
        if self.py.contains("Carlos Kidman"):
            self.manager.results(
                False,
                "Check another website",
                "Something really bad happened.\nNo response.\nAbort",
            )
