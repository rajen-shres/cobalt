import json
import random
import string

from django.db import models
from django.utils import timezone
from django.conf import settings
from post_office.models import Email as PostOfficeEmail

from accounts.models import User
from organisations.models import Organisation


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
    """Stores mappings of users to events and actions"""

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
    """ We only use two states. If a message has been queued but not sent then it will get picked up later
        and sent, even if the code that queued it crashes before it can issue the send() request.
    """

    batch_id = models.CharField("Batch Id", max_length=14, blank=True, null=True)
    recipient = models.CharField("Recipients", max_length=100)
    reply_to = models.CharField(
        "Reply To", max_length=100, blank=True, null=True, default=""
    )
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="member",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="sender",
    )
    created_date = models.DateTimeField("Create Date", default=timezone.now)
    sent_date = models.DateTimeField("Sent Date", blank=True, null=True)


class Email(AbstractEmail):
    def __str__(self):
        return self.subject


class EmailArchive(AbstractEmail):
    def __str__(self):
        return self.subject


class EmailThread(models.Model):
    """Used to keep track of running threads"""

    created_date = models.DateTimeField("Create Date", default=timezone.now)


class BatchID(models.Model):
    """Simple model for unique batch ids"""

    batch_id = models.CharField("Batch Id", max_length=14, blank=True, null=True)
    """batch id links emails together and controls security """

    def create_new(self):
        """create a new batch id"""
        self.batch_id = "%s-%s-%s" % (
            "".join(random.choices(string.ascii_letters + string.digits, k=4)),
            "".join(random.choices(string.ascii_letters + string.digits, k=4)),
            "".join(random.choices(string.ascii_letters + string.digits, k=4)),
        )
        return self.batch_id

    def __str__(self):
        return self.batch_id


class Snooper(models.Model):
    """Stores information from AWS SES about activity with Email

    Also stores the batch id associated with this email which controls
    who sent it and who can access it.

    """

    post_office_email = models.OneToOneField(
        PostOfficeEmail,
        on_delete=models.CASCADE,
        primary_key=True,
    )
    """Link to the email in Django Post Office"""
    ses_sent_at = models.DateTimeField("Sent At", blank=True, null=True)
    ses_delivered_at = models.DateTimeField("Delivered At", blank=True, null=True)
    ses_last_opened_at = models.DateTimeField("Last Opened At", blank=True, null=True)
    ses_open_count = models.IntegerField("Open Count", default=0)
    ses_last_clicked_at = models.DateTimeField("Last Clicked At", blank=True, null=True)
    ses_clicked_count = models.IntegerField("Clicked Count", default=0)
    ses_last_bounce_at = models.DateTimeField("Last Bounce At", blank=True, null=True)
    ses_bounce_reason = models.TextField("Bounce Reason", blank=True, null=True)
    batch_id = models.ForeignKey(
        BatchID, on_delete=models.CASCADE, blank=True, null=True
    )

    def __str__(self):
        return f"Snooper for {self.post_office_email}"


class EmailBatchRBAC(models.Model):
    """Control who can access a batch of emails.

    By default only the global admin group can see an email, this allows specific
    RBAC roles to be granted access.

    """

    batch_id = models.ForeignKey(
        BatchID, on_delete=models.CASCADE, blank=True, null=True
    )
    rbac_role = models.CharField(max_length=300)
    """rbac role to view this batch of emails"""
    meta_sender = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True
    )
    """User who sent this"""
    meta_organisation = models.ForeignKey(
        Organisation, on_delete=models.CASCADE, null=True, blank=True
    )
    """Org who sent this"""

    def __str__(self):
        return f"{self.batch_id} - {self.rbac_role}"


class BlockNotification(models.Model):
    """This is the opposite of what notifications originally did. This maintains a list of things that a user does
    not want to be told about. Originally this was built for conveners who do not want email notifications.

    Setting model_id to None and identifier to either CONVENER_EMAIL_BY_EVENT or CONVENER_EMAIL_BY_ORG has
    the same effect, it stops you getting notified about anything related to any event. To turn this off
    use CONVENER_EMAIL_BY_EVENT set to None so the admin function will work. Changing this manually through Django
    admin is not recommended.

    """

    class Identifier(models.TextChoices):
        # Conveners blocking emails by event_id
        CONVENER_EMAIL_BY_EVENT = "CE"
        # Conveners blocking emails by org_id
        CONVENER_EMAIL_BY_ORG = "CO"

    member = models.ForeignKey(User, on_delete=models.CASCADE)
    """ User who doesn't want notified """

    identifier = models.CharField(max_length=2, choices=Identifier.choices)
    """ One of the enum values, eg CONVENER_EMAIL_BY_EVENT """

    model_id = models.IntegerField(null=True, blank=True)
    """ Specific model_id to block. None to block everything """

    def __str__(self):
        return f"{self.member.full_name} - {self.identifier} - {self.model_id}"


class RealtimeNotificationHeader(models.Model):
    """Optional meta data about RealtimeNotification for use when an administrator
    sends a batch of messages such as the results of a round of an event."""

    admin = models.ForeignKey(User, on_delete=models.CASCADE)
    """Admin who sent the message"""
    description = models.TextField()
    send_status = models.BooleanField(default=False)
    total_record_number = models.IntegerField(default=0)
    """Used for file uploads. Total number of records received through API"""
    attempted_send_number = models.IntegerField(default=0)
    """Number of users we tried to contact. Total - invalid"""
    successful_send_number = models.IntegerField(default=0)
    """How many we think we managed to send"""
    unregistered_users = models.TextField(null=True, blank=True)
    """List of users we couldn't send to as they are unregistered. JSON stored as string"""
    uncontactable_users = models.TextField(null=True, blank=True)
    """List of users we couldn't send to as they aren't set up for it. JSON stored as string"""
    invalid_lines = models.TextField(null=True, blank=True)
    """List of invalid lines in the upload file"""
    created_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.successful_send_number}/{self.total_record_number}] {self.admin.full_name} - {self.created_time.strftime('%Y-%m-%d%H:%M:%S')} - {self.description}"

    def set_unregistered_users(self, data):
        """Convert list to string to save"""
        self.unregistered_users = json.dumps(data)

    def get_unregistered_users(self):
        """Convert string to list to load"""
        return json.loads(self.unregistered_users)

    def set_uncontactable_users(self, data):
        """Convert list to string to save"""
        self.uncontactable_users = json.dumps(data)

    def get_uncontactable_users(self):
        """Convert string to list to load"""
        return json.loads(self.uncontactable_users)

    def set_invalid_lines(self, data):
        """Convert list to string to save"""
        self.invalid_lines = json.dumps(data)

    def get_invalid_lines(self):
        """Convert string to list to load"""
        return json.loads(self.invalid_lines)


class RealtimeNotification(models.Model):
    """Logging for realtime notifications such as SMS or in app messages to phones"""

    header = models.ForeignKey(
        RealtimeNotificationHeader, on_delete=models.CASCADE, null=True, blank=True
    )
    """Optional header record with meta data"""
    member = models.ForeignKey(User, on_delete=models.CASCADE, related_name="rt_member")
    """Member who received the message"""
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name="rt_admin")
    """Admin who sent the message"""
    msg = models.TextField()
    status = models.BooleanField(default=False)
    created_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.member.full_name} - {self.created_time.strftime('%Y-%m-%d%H:%M:%S')}"
