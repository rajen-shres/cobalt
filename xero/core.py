import json
import logging
from datetime import timedelta

import requests
import base64

from django.utils.timezone import now

from cobalt.settings import XERO_CLIENT_ID, XERO_CLIENT_SECRET, XERO_TENANT_NAME
from xero.models import XeroCredentials

logger = logging.getLogger("etime")


class XeroApi:
    def __init__(self):

        # load credentials
        credentials, _ = XeroCredentials.objects.get_or_create()
        self.access_token = credentials.access_token
        self.refresh_token = credentials.refresh_token
        self.tenant_id = credentials.tenant_id

        # Static data
        self.redirect_url = "http://localhost:8000/xero/callback"
        self.token_refresh_url = "https://identity.xero.com/connect/token"
        self.exchange_code_url = "https://identity.xero.com/connect/token"
        self.connections_url = "https://api.xero.com/connections"
        self.authorisation_url = "https://login.xero.com/identity/connect/authorize"
        self.scope = "offline_access accounting.transactions accounting.contacts payroll.employees payroll.payruns payroll.payslip payroll.timesheets payroll.settings"
        self.b64_id_secret = base64.b64encode(
            bytes(f"{XERO_CLIENT_ID}:{XERO_CLIENT_SECRET}", "utf-8")
        ).decode("utf-8")
        self.xero_auth_url = f"{self.authorisation_url}?response_type=code&client_id={XERO_CLIENT_ID}&redirect_uri={self.redirect_url}&scope={self.scope}&state=123"

    def headers(self):
        """return API headers"""

        return {
            "Authorization": f"Bearer {self.access_token}",
            "Xero-tenant-id": self.tenant_id,
            "Accept": "application/json",
        }

    def refresh_using_authorisation_code(self, authorisation_code):
        """pass Xero an authorisation code and get an access token back"""

        # Now we need to exchange the code for a token
        response = requests.post(
            self.exchange_code_url,
            headers={"Authorization": f"Basic {self.b64_id_secret}"},
            data={
                "grant_type": "authorization_code",
                "code": authorisation_code,
                "redirect_uri": self.redirect_url,
            },
        )

        json_response = response.json()

        print(json_response)

        access_token = json_response["access_token"]
        refresh_token = json_response["refresh_token"]

        credentials, _ = XeroCredentials.objects.get_or_create()
        credentials.authorisation_code = authorisation_code
        credentials.access_token = access_token
        credentials.refresh_token = refresh_token
        credentials.expires = now() + timedelta(seconds=json_response["expires_in"] - 2)
        credentials.save()

        self.access_token = access_token
        self.refresh_token = refresh_token

        logger.info("Updated access token using authorisation code")

    def refresh_xero_tokens(self):
        """the access token expires quickly but can be reset using the refresh token"""

        # See if still valid
        credentials, _ = XeroCredentials.objects.get_or_create()
        if credentials.expires and credentials.expires > now():
            logger.info("Access token is still valid. Not refreshing.")
            return {"message": "Access token is still valid. Not refreshing."}

        logger.info("Refreshing access token")

        # Update access token using refresh token
        response = requests.post(
            self.token_refresh_url,
            headers={
                "Authorization": f"Basic {self.b64_id_secret}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "refresh_token", "refresh_token": self.refresh_token},
        )

        json_response = response.json()
        if "access_token" not in json_response:
            return json_response

        credentials.access_token = json_response["access_token"]
        credentials.expires = now() + timedelta(seconds=json_response["expires_in"] - 2)
        credentials.refresh_token = json_response["refresh_token"]
        credentials.save()

        self.access_token = credentials.access_token
        self.refresh_token = credentials.refresh_token

        return json_response

    def set_tenant_id(self):
        """get the tenant id from Xero. We only support one tenant at a time"""

        logger.info("Getting tenants")

        response = requests.get(
            self.connections_url,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
        )

        json_response = response.json()

        for tenant in json_response:

            if tenant["tenantName"] == XERO_TENANT_NAME:
                self.tenant_id = tenant["tenantId"]
                credentials, _ = XeroCredentials.objects.get_or_create()
                credentials.tenant_id = self.tenant_id
                credentials.save()
                logger.info(f"Updated tenant id for {XERO_TENANT_NAME}")

                return

        logger.error(f"No tenants found matching {XERO_TENANT_NAME}")

    def xero_api_get(self, url):
        """generic api call for GET"""
        self.refresh_xero_tokens()
        logger.info(url)
        return requests.get(url, headers=self.headers()).json()

    def xero_api_post(self, url, json_data):
        """generic api call for POST"""

        self.refresh_xero_tokens()
        print(json_data)
        print(json.dumps(json_data))

        logger.info(url)

        return requests.post(
            url, headers=self.headers(), data=json.dumps(json_data)
        ).json()
