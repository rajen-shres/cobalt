from datetime import timedelta

from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils.timezone import now

from organisations.models import Organisation
from xero.core import XeroApi
from xero.models import XeroCredentials


def initialise(request):
    """direct a user to grant initial permissions for us from xero"""

    auth_url = XeroApi().xero_auth_url

    return render(request, "xero/initialise.html", {"auth_url": auth_url})


def callback(request):
    """initial callback when a user is sent to Xero to provide access for us"""

    # Get data
    authorisation_code = request.GET.get("code")

    xero = XeroApi()
    xero.refresh_using_authorisation_code(authorisation_code)
    xero.set_tenant_id()

    return redirect(reverse("xero:xero_home"))


def home(request):
    """Main page for Xero"""
    xero = XeroApi()
    return render(request, "xero/home.html", {"xero": xero})


def home_configuration_htmx(request):
    """HTMX table with config data"""

    xero = XeroApi()
    xero_credentials = XeroCredentials.objects.first()
    return render(
        request,
        "xero/home_configuration_htmx.html",
        {"xero": xero, "xero_credentials": xero_credentials},
    )


def refresh_keys_htmx(request):
    # refresh the keys

    xero = XeroApi()
    json_data = xero.refresh_xero_tokens()

    response = render(request, "xero/json_data.html", {"json_data": json_data})

    # Tell the page to update the config part
    response["HX-Trigger"] = """{{"update_config": "true"}}"""

    return response


def run_xero_api_htmx(request):
    """generic function to run some api calls"""

    xero = XeroApi()
    cmd = request.POST.get("cmd")

    json_data = {}

    if cmd == "list_clubs":
        json_data = xero.xero_api_get("https://api.xero.com/api.xro/2.0/Contacts")

    if cmd == "create_club":

        # isSupplier doesn't seem to work
        json_data = {
            "Contacts": [
                {
                    "AccountNumber": "2-999",
                    "ContactStatus": "ACTIVE",
                    "Name": "Payments Bridge Club",
                    "BankAccountDetails": "",
                }
            ]
        }

        json_data = xero.xero_api_post(
            "https://api.xero.com/api.xro/2.0/Contacts", json_data=json_data
        )

        print(json_data)

        contact_id = json_data["Contacts"][0]["ContactID"]
        print(contact_id)

        club = Organisation.objects.filter(name="Payments Bridge Club").first()
        club.xero_contact_id = contact_id
        club.save()

    if cmd == "create_invoice":

        club = Organisation.objects.filter(name="Payments Bridge Club").first()

        json_data = {
            "Invoices": [
                {
                    "Type": "ACCPAY",
                    "Contact": {
                        "ContactID": club.xero_contact_id,
                    },
                    "LineItems": [
                        {
                            "Description": "ABF Settlement for June",
                            "Quantity": 1,
                            "UnitAmount": 344.55,
                            "AccountCode": "200",
                            "TaxType": "NONE",
                            "LineAmount": 344.55,
                        }
                    ],
                    "Date": f"{now():%Y-%m-%d}",
                    "DueDate": f"{now() + timedelta(days=15):%Y-%m-%d}",
                    "Reference": "ABF Settlement",
                    "Status": "AUTHORISED",
                }
            ]
        }
        json_data = xero.xero_api_post(
            "https://api.xero.com/api.xro/2.0/Invoices", json_data=json_data
        )

    response = render(request, "xero/json_data.html", {"json_data": json_data})

    # Tell the page to update the config part
    response["HX-Trigger"] = """{{"update_config": "true"}}"""

    return response
