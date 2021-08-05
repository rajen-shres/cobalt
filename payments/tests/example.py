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

    def ex(self):
        print("inside ex")
        response = self.manager.client.get("/dashboard/")
        self.manager.results(response.status_code, "Load Dashboard")

        self.py.visit("https://qap.dev")
        self.py.get('a[href="/about"]').hover()
        self.py.get('a[href="/leadership"][class^="Header-nav"]').click()
        if self.py.contains("Carlos Kidman"):
            self.manager.results(True, "Check a website")

    def ex2(self):
        print("inside e2x")
        response = self.manager.client.get("/dashboard/")
        self.manager.results(response.status_code, "Load Dashboard")

        self.py.visit("https://qap.dev")
        self.py.get('a[href="/about"]').hover()
        self.py.get('a[href="/leadership"][class^="Header-nav"]').click()
        if self.py.contains("Carlos Kidman"):
            self.manager.results(False, "Check another website")
