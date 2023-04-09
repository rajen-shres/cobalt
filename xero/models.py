from django.db import models


class XeroCredentials(models.Model):
    """persistent store for Xero credentials"""

    # The authorisation code is given to use by the user who provides authorisation. We get this from a callback
    authorisation_code = models.CharField(max_length=100, blank=True, default="")

    # The access token is enormous and expires quickly
    access_token = models.CharField(max_length=2000, blank=True, default="")

    # We store the expiry to see if it is still valid for quick succession calls
    expires = models.DateTimeField(null=True)

    # The refresh token is used to get a new (not expired) access_token
    refresh_token = models.CharField(max_length=100, blank=True, default="")

    # The tenant id identifies the company we are using
    tenant_id = models.CharField(max_length=100, blank=True, default="")

    def __str__(self):
        return "Xero Credentials"
