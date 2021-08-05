import inspect
from pprint import pprint

from django.test import Client
from django.test.utils import setup_test_environment
from django.urls import reverse

from accounts.models import User
from payments.forms import MemberTransfer
from payments.models import MemberTransaction

setup_test_environment()


class CobaltTestManager:
    """
    These tests access the app from within Django and through the Client object.
    This is the similar to accessing the app from the web but doesn't involve any
    UI aspects. Basically this testing is at the data level, not the UI level.
    We can trigger code by sending in POST or GET requests and we can check the
    parameters that were sent to the template as well as see the generated code.
    This makes it cleaner to test logic without worrying about the UI parts and
    means we are independent of the UI itself.

    This is entirely server side testing and tests no Javascript code on the
    client.
    """

    def __init__(self):
        self.client = Client()
        self.login("100")
        self.success = []
        self.failure = []

    def login(self, username):
        test_user = User.objects.filter(username=username).first()
        self.client.force_login(test_user)

    def results(self, status, msg, details=None):
        """handle logging results

        args:
            status: Int or Boolean
                status can either be a number,e.g. from response.status_code, with 200
                being taken as True and anything else as False. OR a Boolean if the
                calling function wants to handle things itself.
            msg: Str. High level message on what this tests
            details: List. List of specific sub-tests performed.

        """

        # Get name of calling function
        item = {"function": inspect.stack()[1][3], "msg": msg, "details": details}

        # work out which list to add this to
        if type(status) == int and status == 200 or type(status) != int and status:
            self.success.append(item)
        else:
            self.failure.append(item)

    def report(self):
        """Report on total test findings"""
        if not self.failure:
            print("Success")
            return

        count_success = len(self.success)
        count_failure = len(self.failure)
        count_total = count_success + count_failure
        print(f"Failed {count_failure}/{count_total}")
        for item in self.failure:
            print(f"Failed {item['function']} - {item['msg']}")
            if item["details"]:
                for error in item["details"]:
                    print(f"  {error['status']}: {error['msg']}")

    def report_html(self):
        """return report as html"""

        if self.failure:
            count_success = len(self.success)
            count_failure = len(self.failure)
            count_total = count_success + count_failure
            html = f"<h2>Failed {count_failure}/{count_total}</h2>\n"
            for item in self.failure:
                html += f"Failed {item['function']} - {item['msg']}\n"
                if item["details"]:
                    for error in item["details"]:
                        html += f"  {error['status']}: {error['msg']}\n"
        else:
            html = "<h1>Success</h1>"
        return html

    def run(self):
        self.run_dashboard()
        self.run_dashboard_details()
        self.run_forums()
        self.run_forums_details()
        self.run_member_transfer()
        return not self.failure

    def run_dashboard(self):
        response = self.client.get("/dashboard/")
        self.results(response.status_code, "Load Dashboard")

    def run_dashboard_details(self):
        """Go to the dashboard and check basic details are present. Currently only balance can be checked"""
        response = self.client.get("/dashboard/")
        details = []
        passing = True

        if response.context["payments"]["balance"] == 400:
            detail = {"status": True, "msg": "Bridge Credit balance is correct"}
        else:
            detail = {
                "status": False,
                "msg": f"Incorrect Bridge Credit amount - expected 400, got {response.context['payments']['balance']}",
            }
            passing = False
        details.append(detail)

        self.results(passing, "Load Dashboard and check details", details)

    def run_forums(self):
        response = self.client.get("/forums/")
        self.results(response.status_code, "View main forum page")

    def run_forums_details(self):
        """Go to Forums and check basic details are present."""
        response = self.client.get("/forums/")
        details = []
        passing = True

        if response.context["forums"][0]["title"] == "System Announcements":
            detail = {"status": True, "msg": "Forum 1 correct"}
        else:
            detail = {
                "status": False,
                "msg": f"Forum 1 wrong title. Expected 'System Announcements', got {response.context['forums'][0]['title']}",
            }
            passing = False
        details.append(detail)

        self.results(passing, "Load Dashboard and check details", details)

    def run_member_transfer(self):
        """perform a member transfer and check results"""

        url = reverse("payments:member_transfer")

        betty = User.objects.filter(username="101").first()

        form_data = {
            "transfer_to": betty,
            "amount": 54.45,
            "description": "test transfer",
        }
        form = MemberTransfer(data=form_data)
        print("Checking form...")
        print(form.is_valid())

        form_data = {
            "transfer_to": betty.id,
            "amount": 54.45,
            "description": "test transfer",
        }

        print("Checking POST...")
        response = self.client.post(url, form_data)

        print(response)

        print("check transactions...")
        betty_tran = (
            MemberTransaction.objects.filter(member=betty)
            .order_by("-created_date")
            .first()
        )
        print(betty_tran.description, betty_tran.amount, betty_tran.other_member)

        print("Checking statements...")

        url = reverse("payments:statement_admin_view", kwargs={"member_id": betty.id})
        response = self.client.get(url)
        pprint(response.context["things"])
