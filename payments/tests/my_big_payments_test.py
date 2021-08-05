import time

from django.test import Client

from accounts.models import User


class PaymentsTest37:
    def __init__(self, manager):
        self.manager = manager
        self.client = self.manager.client
        self.py = self.manager.py

    def wester_hails_riot(self):
        self.py.visit(f"{self.manager.base_url}/dashboard")
        balance = self.py.get("#id_account_balance")
        time.sleep(10)
        print(balance.text())

    # def fishing_on_a_sunday(self):
    #     print("inside e2x")
    #     response = self.manager.client.get("/dashboard/")
    #     self.manager.results(response.status_code, "Perform difficult calcs")
    #
    #     self.py.visit("https://qap.dev")
    #     self.py.get('a[href="/about"]').hover()
    #     self.py.get('a[href="/leadership"][class^="Header-nav"]').click()
    #     if self.py.contains("Carlos Kidman"):
    #         self.manager.results(False, "Check another website", "Something really bad happened.\nNo response.\nAbort")
