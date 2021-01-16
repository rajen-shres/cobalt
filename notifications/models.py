from django.db import models
from django.utils import timezone
from django.conf import settings


class InAppNotification(models.Model):
    """Temporary storage for notification messages.

    Stores any event that a Cobalt module wants to notify a user about.
    """

    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    message = models.CharField("Message", max_length=100)

    link = models.CharField("Link", max_length=50, blank=True, null=True)

    acknowledged = models.BooleanField(default=False)

    created_date = models.DateTimeField("Creation Date", default=timezone.now)


class NotificationMapping(models.Model):
    """ Stores mappings of users to events and actions  """

    NOTIFICATION_TYPES = [("SMS", "SMS Message"), ("Email", "Email Message")]

    APPLICATION_NAMES = [("Forums", "Forums"), ("Payments", "Payments")]

    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    application = models.CharField(
        "Application", max_length=20, choices=APPLICATION_NAMES
    )
    """ Cobalt application name """

    event_type = models.CharField("Event Type", max_length=50)
    """ Event type as set by the application. eg. forum.post.new """

    topic = models.CharField("Topic", max_length=20)
    """ Level 1 event in application """

    subtopic = models.CharField("Sub-Topic", max_length=20, blank=True, null=True)
    """ Level 2 event in application """

    notification_type = models.CharField(
        "Notification Type", max_length=5, choices=NOTIFICATION_TYPES, default="Email"
    )
    """ How to notify the member """


class AbstractEmail(models.Model):
    """Stores emails so that the sending of emails is decoupled from their production.
    This is needed as there can be delays sending email which affect client responsiveness.
    See the documentation for more information especially around setting up
    the system so that emails get sent and don't sit in the queue forever.
    This Abstract class is made concrete as Email and EmailArchive.
    """

    subject = models.CharField("Subject", max_length=200)
    message = models.TextField("Message")
    status = models.CharField(
        "Status",
        max_length=6,
        choices=[("Queued", "Queued to Send"), ("Sent", "Sent")],
        default="Queued",
    )
    recipient = models.CharField("Recipients", max_length=100)
    reply_to = models.CharField(
        "Reply To", max_length=100, blank=True, null=True, default=""
    )
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="member",
    )
    created_date = models.DateTimeField("Create Date", default=timezone.now)
    sent_date = models.DateTimeField("Sent Date", blank=True, null=True)


class Email(AbstractEmail):
    def __str__(self):
        return self.subject


class EmailArchive(AbstractEmail):
    def __str__(self):
        return self.subject
