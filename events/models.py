from django.db import models
from django.utils import timezone
from django.contrib.postgres.fields import ArrayField
from django.contrib.humanize.templatetags.humanize import ordinal
from utils.templatetags.cobalt_tags import cobalt_credits
from organisations.models import Organisation
from accounts.models import User
from payments.models import MemberTransaction
from cobalt.settings import (
    GLOBAL_ORG,
    TIME_ZONE,
    BRIDGE_CREDITS,
)
from utils.utils import cobalt_round
import datetime
import pytz
from rbac.core import rbac_user_has_role

PAYMENT_STATUSES = [
    ("Paid", "Entry Paid"),
    ("Pending Manual", "Pending Manual Payment"),
    ("Unpaid", "Entry Unpaid"),
    ("Free", "Free"),
]

ENTRY_STATUSES = [
    ("Pending", "Pending"),
    ("Complete", "Complete"),
    ("Cancelled", "Cancelled"),
]

# my-system-dollars - you can pay for your own or other people's entries with
# your money.
# their-system-dollars - you can use a team mates money to pay for their
# entry if you have permission
# other-system-dollars - we're not paying and we're not using their account
# to pay
PAYMENT_TYPES = [
    (
        "my-system-dollars",
        BRIDGE_CREDITS,
    ),
    ("their-system-dollars", f"Their {BRIDGE_CREDITS}"),
    ("other-system-dollars", "TBA"),
    ("bank-transfer", "Bank Transfer"),
    ("off-system-pp", "Club PP System"),
    ("cash", "Cash"),
    ("cheque", "Cheque"),
    ("unknown", "Unknown"),
    ("Free", "Free"),
]
CONGRESS_STATUSES = [
    ("Draft", "Draft"),
    ("Published", "Published"),
    ("Closed", "Closed"),
]
EVENT_TYPES = [
    ("Open", "Open"),
    ("Restricted", "Restricted"),
    ("Novice", "Novice"),
    ("Senior", "Senior"),
    ("Youth", "Youth"),
    ("Rookies", "Rookies"),
    ("Veterans", "Veterans"),
    ("Womens", "Womens"),
    ("Intermediate", "Intermediate"),
]
EVENT_PLAYER_FORMAT = [
    #    ("Individual", "Individual"),
    ("Pairs", "Pairs"),
    ("Teams of 3", "Teams of Three"),
    ("Teams", "Teams"),
]
EVENT_PLAYER_FORMAT_SIZE = {
    "Individual": 1,
    "Pairs": 2,
    "Teams of 3": 3,
    "Teams": 6,
}

PEOPLE_DEFAULT = """<table class="table"><tbody><tr><td><span style="font-weight: normal;">
Organiser:</span></td><td><span style="font-weight: normal;">Jane Doe</span></td>
</tr><tr><td><span style="font-weight: normal;">Phone:</span></td><td>
<span style="font-weight: normal;">040404040444</span></td></tr><tr><td>
<span style="font-weight: normal;">Email:</span></td><td><span style="font-weight: normal;">
me@club.com</span></td></tr><tr><td><span style="font-weight: normal;">
Chief Tournament Director:</span></td><td><span style="font-weight: normal;">
Alan Partidge</span></td></tr></tbody></table><p><br></p>"""


class CongressMaster(models.Model):
    """Master List of congresses. E.g. GCC. This is not an instance
    of a congress, just a list of the regular recurring ones.
    Congresses can only belong to one club at a time. Control for
    who can setup a congress as an instance of a congress master
    is handled by who is a convener for a club"""

    name = models.CharField("Congress Master Name", max_length=100)
    org = models.ForeignKey(Organisation, on_delete=models.CASCADE)
    # status = models.CharField(
    #         "Status", max_length=14, choices=[("Open", "Open"), ("Disabled", "Disabled")], default="Open"
    #     )

    def __str__(self):
        return self.name


class Congress(models.Model):
    """A specific congress including year

    We set all values to be optional so we can use the wizard format and
    save partial data as we go. The validation for completeness of data
    lies in the view."""

    name = models.CharField("Name", max_length=100)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    date_string = models.CharField("Dates", max_length=100, null=True, blank=True)
    congress_master = models.ForeignKey(
        CongressMaster, on_delete=models.CASCADE, null=True, blank=True
    )
    year = models.IntegerField("Congress Year", null=True, blank=True)
    venue_name = models.CharField("Venue Name", max_length=100, null=True, blank=True)
    venue_location = models.CharField(
        "Venue Location", max_length=100, null=True, blank=True
    )
    venue_transport = models.TextField("Venue Transport", null=True, blank=True)
    venue_catering = models.TextField("Venue Catering", null=True, blank=True)
    venue_additional_info = models.TextField(
        "Venue Additional Information", null=True, blank=True
    )
    sponsors = models.TextField("Sponsors", null=True, blank=True)
    additional_info = models.TextField(
        "Congress Additional Information", null=True, blank=True
    )
    raw_html = models.TextField("Raw HTML", null=True, blank=True)
    people = models.TextField("People", null=True, blank=True, default=PEOPLE_DEFAULT)

    general_info = models.TextField("General Information", null=True, blank=True)
    links = models.TextField("Links", null=True, blank=True)
    latest_news = models.TextField("Latest News", null=True, blank=True)
    payment_method_system_dollars = models.BooleanField(default=True)
    payment_method_bank_transfer = models.BooleanField(default=False)
    bank_transfer_details = models.TextField(
        "Bank Transfer Details", null=True, blank=True
    )
    payment_method_cash = models.BooleanField(default=False)
    payment_method_cheques = models.BooleanField(default=False)
    payment_method_off_system_pp = models.BooleanField(default=False)
    cheque_details = models.TextField("Cheque Details", null=True, blank=True)
    allow_early_payment_discount = models.BooleanField(default=False)
    early_payment_discount_date = models.DateField(
        "Last day for early discount", null=True, blank=True
    )
    allow_youth_payment_discount = models.BooleanField(default=False)
    youth_payment_discount_date = models.DateField(
        "Date for age check", null=True, blank=True
    )
    youth_payment_discount_age = models.IntegerField("Cut off age", default=30)
    senior_date = models.DateField("Date for age check", null=True, blank=True)
    senior_age = models.IntegerField("Cut off age", default=60)
    # Open and close dates can be overriden at the event level
    entry_open_date = models.DateField(null=True, blank=True)
    entry_close_date = models.DateField(null=True, blank=True)
    automatic_refund_cutoff = models.DateField(null=True, blank=True)
    allow_partnership_desk = models.BooleanField(default=False)
    author = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="author", null=True, blank=True
    )
    created_date = models.DateTimeField(default=timezone.now)
    last_updated_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="last_updated_by",
    )
    last_updated = models.DateTimeField(default=timezone.now)
    status = models.CharField(
        "Congress Status", max_length=10, choices=CONGRESS_STATUSES, default="Draft"
    )

    class Meta:
        verbose_name_plural = "Congresses"

    def __str__(self):
        return self.name

    def user_is_convener(self, user):
        """ check if a user has convener rights to this congress """

        role = "events.org.%s.edit" % self.congress_master.org.id
        return rbac_user_has_role(user, role)

    def get_payment_methods(self):
        """get a list of payment types for this congress. Excludes other-system-dollars
        as this isn't applicable for the logged in user and is easier to add to the
        list than remove"""

        pay_methods = []
        if self.payment_method_system_dollars:
            pay_methods.append(("my-system-dollars", f"My {BRIDGE_CREDITS}"))
        if self.payment_method_bank_transfer:
            pay_methods.append(("bank-transfer", "Bank Transfer"))
        if self.payment_method_cash:
            pay_methods.append(("cash", "Cash on the day"))
        if self.payment_method_cheques:
            pay_methods.append(("cheque", "Cheque"))
        if self.payment_method_off_system_pp:
            pay_methods.append(("off-system-pp", "Club PP System"))

        return pay_methods


class Event(models.Model):
    """ An event within a congress """

    congress = models.ForeignKey(Congress, on_delete=models.CASCADE)
    event_name = models.CharField("Event Name", max_length=100)
    description = models.CharField("Description", max_length=400, null=True, blank=True)
    max_entries = models.IntegerField("Maximum Entries", null=True, blank=True)
    event_type = models.CharField(
        "Event Type", max_length=14, choices=EVENT_TYPES, null=True, blank=True
    )
    # Open and close dates can be overriden at the event level
    entry_open_date = models.DateField(null=True, blank=True)
    entry_close_date = models.DateField(null=True, blank=True)
    entry_fee = models.DecimalField("Entry Fee", max_digits=12, decimal_places=2)
    entry_early_payment_discount = models.DecimalField(
        "Early Payment Discount", max_digits=12, decimal_places=2, null=True, blank=True
    )
    entry_youth_payment_discount = models.IntegerField(
        "Youth Discount Percentage", null=True, blank=True
    )
    player_format = models.CharField(
        "Player Format",
        max_length=14,
        choices=EVENT_PLAYER_FORMAT,
    )
    free_format_question = models.CharField(
        "Free Format Question", max_length=60, null=True, blank=True
    )

    def __str__(self):
        return "%s - %s" % (self.congress, self.event_name)

    def is_open(self):
        """ check if this event is taking entries today """

        today = timezone.now().date()

        open_date = self.entry_open_date
        if not open_date:
            open_date = self.congress.entry_open_date
            if open_date:
                if today < open_date:
                    return False

        close_date = self.entry_close_date
        if not close_date:
            close_date = self.congress.entry_close_date
        if close_date:
            if today > close_date:
                return False

        # check start date of event
        start_date = self.start_date()
        print("Start date:")
        print(start_date)
        print("Today:")
        print(today)
        if start_date and start_date < today:  # event started
            return False
        elif start_date == today:
            start_time = self.start_time()
            print("Start time:")
            print(start_time)

            print("Now:")
            print(timezone.now().time())

            if start_time and start_time < timezone.now().time():
                return False

        return True

    def entry_fee_for(self, user, check_date=None):
        """return entry fee for user based on age and date. Also any EventPlayerDiscount applied
        We accept a check_date to work out what the entry fee would be for that date, if not
        provided then we use today."""

        if not check_date:
            check_date = timezone.now().date()

        # default
        discount = 0.0
        reason = "Full fee"
        description = reason
        players_per_entry = EVENT_PLAYER_FORMAT_SIZE[self.player_format]
        # Need a better approach for teams
        if self.player_format == "Teams":
            players_per_entry = 4
        entry_fee = cobalt_round(self.entry_fee / players_per_entry)

        # date
        if self.congress.allow_early_payment_discount:
            if self.congress.early_payment_discount_date >= check_date:
                entry_fee = (
                    self.entry_fee - self.entry_early_payment_discount
                ) / players_per_entry
                entry_fee = cobalt_round(entry_fee)
                reason = "Early discount"
                discount = float(self.entry_fee) / players_per_entry - float(entry_fee)
                description = "Early discount " + cobalt_credits(discount)

        # youth discounts apply after early entry discounts
        if self.congress.allow_youth_payment_discount:
            if user.dob:  # skip if no date of birth set
                dob = datetime.datetime.combine(user.dob, datetime.time(0, 0))
                dob = timezone.make_aware(dob, pytz.timezone(TIME_ZONE))
                ref_date = dob.replace(
                    year=dob.year + self.congress.youth_payment_discount_age
                )
                if self.congress.youth_payment_discount_date <= ref_date.date():
                    entry_fee = (
                        float(entry_fee)
                        * float(self.entry_youth_payment_discount)
                        / 100.0
                    )
                    entry_fee = cobalt_round(entry_fee)
                    discount = float(self.entry_fee) / players_per_entry - entry_fee
                    if reason == "Early discount":
                        reason = "Youth+Early discount"
                        description = "Youth+Early discount " + cobalt_credits(discount)
                    else:
                        reason = "Youth discount"
                        description = (
                            "Youth discount %s%%" % self.entry_youth_payment_discount
                        )

        # EventPlayerDiscount
        event_player_discount = (
            EventPlayerDiscount.objects.filter(event=self).filter(player=user).first()
        )

        if event_player_discount:
            discount_fee = cobalt_round(event_player_discount.entry_fee)
            if discount_fee < entry_fee:
                entry_fee = discount_fee
                reason = event_player_discount.reason
                description = f"Manual override {reason}"

        return entry_fee, discount, reason[:40], description

    def already_entered(self, user):
        """ check if a user has already entered """

        event_entry_list = self.evententry_set.all().values_list("id")

        event_entry_player = (
            EventEntryPlayer.objects.filter(player=user)
            .filter(event_entry__in=event_entry_list)
            .exclude(event_entry__entry_status="Cancelled")
            .first()
        )

        if event_entry_player:
            return event_entry_player.event_entry
        else:
            return None

    def start_time(self):
        """ return the start time of this event """
        session = Session.objects.filter(event=self)
        if session:
            return session.earliest("session_date").session_start
        else:
            return None

    def start_date(self):
        """ return the start date of this event """
        session = Session.objects.filter(event=self)
        if session:
            return session.earliest("session_date").session_date
        else:
            return None

    def end_date(self):
        """ return the end date of this event """
        session = Session.objects.filter(event=self)
        if session:
            return session.latest("session_date").session_date
        else:
            return None

    def print_dates(self):
        """ returns nicely formatted date string for event """
        start = self.start_date()
        end = self.end_date()

        if not start:  # no start will also mean no end
            return None

        if start == end:
            return "%s %s" % (ordinal(start.strftime("%d")), start.strftime("%B %Y"))

        start_day = ordinal(start.strftime("%d"))
        start_month = start.strftime("%B")
        start_year = start.strftime("%Y")
        end_day = ordinal(end.strftime("%d"))
        end_month = end.strftime("%B")
        end_year = end.strftime("%Y")

        if start_year == end_year:
            start_year = ""

        if start_month == end_month:
            start_month = ""
        else:
            start_month = " " + start_month
            if start_year != "":
                start_year = " " + start_year

        return (
            f"{start_day}{start_month}{start_year} to {end_day} {end_month} {end_year}"
        )

    def entry_status(self, user):
        """ returns the status of the team/pairs/individual entry """

        event_entry_player = (
            EventEntryPlayer.objects.filter(player=user)
            .exclude(event_entry__entry_status="Cancelled")
            .filter(event_entry__event=self)
            .first()
        )

        if event_entry_player:
            return event_entry_player.event_entry.entry_status

        return None

    def is_full(self):
        """ check if event is already full """

        if self.max_entries is None:
            return False

        entries = (
            EventEntry.objects.filter(event=self)
            .exclude(entry_status="Cancelled")
            .count()
        )
        if entries >= self.max_entries:
            return True
        else:
            return False


class Category(models.Model):
    """ Event Categories such as <100 MPs or club members etc. Free format."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    description = models.CharField("Event Category", max_length=30)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.description


class Session(models.Model):
    """ A session within an event """

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    session_date = models.DateField()
    session_start = models.TimeField()
    session_end = models.TimeField(null=True, blank=True)


#
# class EventEntryType(models.Model):
#     """ A type of event entry - e.g. full, junior, senior """
#
#     event = models.ForeignKey(Event, on_delete=models.CASCADE)
#     event_entry_type = models.CharField("Event Entry Type", max_length=20)
#     entry_fee = models.DecimalField("Full Entry Fee", decimal_places=2, max_digits=10)
#
#     def __str__(self):
#         return "%s - %s" % (self.event, self.event_entry_type)


class EventEntry(models.Model):
    """ An entry to an event """

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    entry_status = models.CharField(
        "Entry Status", max_length=20, choices=ENTRY_STATUSES, default="Pending"
    )
    primary_entrant = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, null=True, blank=True
    )
    free_format_answer = models.CharField(
        "Free Format Answer", max_length=60, null=True, blank=True
    )
    notes = models.TextField("Notes", null=True, blank=True)

    class Meta:
        verbose_name_plural = "Event entries"

    def __str__(self):
        return "%s - %s - %s" % (
            self.event.congress,
            self.event.event_name,
            self.primary_entrant,
        )

    first_created_date = models.DateTimeField(default=timezone.now)
    entry_complete_date = models.DateTimeField(null=True, blank=True)

    def check_if_paid(self):
        """go through sub level event entry players and see if this is now
        complete as well."""

        all_complete = True
        for event_entry_player in self.evententryplayer_set.all():
            if event_entry_player.payment_status not in ["Paid", "Free"]:
                all_complete = False
                break
        if all_complete:
            self.entry_status = "Complete"
            self.entry_complete_date = timezone.now()
        else:
            self.entry_status = "Pending"
        self.save()

    def user_can_change(self, member):
        """Check if a user has access to change this entry.

        Either the primary_entrant who created the entry or
        any of the players can change the entry."""

        if member == self.primary_entrant:
            return True

        allowed = (
            EventEntryPlayer.objects.filter(event_entry=self)
            .filter(player=member)
            .exclude(event_entry__entry_status="Cancelled")
            .count()
        )

        return allowed


class EventEntryPlayer(models.Model):
    """ A player who is entering an event """

    event_entry = models.ForeignKey(EventEntry, on_delete=models.CASCADE)
    player = models.ForeignKey(User, on_delete=models.CASCADE, related_name="player")
    paid_by = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True, related_name="paid_by"
    )
    payment_type = models.CharField(
        "Payment Type", max_length=20, choices=PAYMENT_TYPES, default="Unknown"
    )
    payment_status = models.CharField(
        "Payment Status", max_length=20, choices=PAYMENT_STATUSES, default="Unpaid"
    )
    batch_id = models.CharField(
        "Payment Batch ID", max_length=40, null=True, blank=True
    )
    reason = models.CharField("Entry Fee Reason", max_length=40, null=True, blank=True)
    entry_fee = models.DecimalField(
        "Entry Fee", decimal_places=2, max_digits=10, null=True, blank=True
    )
    payment_received = models.DecimalField(
        "Payment Received", decimal_places=2, max_digits=10, default=0.0
    )
    first_created_date = models.DateTimeField(default=timezone.now)
    entry_complete_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return "%s - %s" % (self.event_entry, self.player)


class PlayerBatchId(models.Model):
    """Maps a batch Id associated with a payment to the user who made the
    payment. We use the same approach for all players so can't assume it
    will be the primary entrant."""

    player = models.ForeignKey(User, on_delete=models.CASCADE)
    batch_id = models.CharField(
        "Payment Batch ID", max_length=40, null=True, blank=True
    )


class CongressLink(models.Model):
    """ Link Items for Congresses """

    congress = models.ForeignKey(Congress, on_delete=models.CASCADE)
    link = models.CharField("Congress Link", max_length=100)

    def __str__(self):
        return "%s" % (self.congress)


class CongressNewsItem(models.Model):
    """ News Items for Congresses """

    congress = models.ForeignKey(Congress, on_delete=models.CASCADE)
    text = models.TextField()

    def __str__(self):
        return "%s" % (self.congress)


class BasketItem(models.Model):
    """ items in a basket. We don't define basket itself as it isn't needed """

    player = models.ForeignKey(User, on_delete=models.CASCADE)
    event_entry = models.ForeignKey(EventEntry, on_delete=models.CASCADE)


class EventLog(models.Model):
    """ log of things that happen within an event """

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    actor = models.ForeignKey(User, on_delete=models.CASCADE)
    event_entry = models.ForeignKey(
        EventEntry, on_delete=models.SET_NULL, null=True, blank=True
    )
    action_date = models.DateTimeField(default=timezone.now)
    action = models.TextField("Action")

    def __str__(self):
        return "%s - %s" % (self.event, self.actor)


class EventPlayerDiscount(models.Model):
    """Maps player discounts to events. For example if someone is given free
    entry to an event."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    player = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="player_discount"
    )
    admin = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="admin_discount"
    )
    entry_fee = models.DecimalField("Entry Fee", max_digits=12, decimal_places=2)
    reason = models.CharField("Reason", max_length=200)
    create_date = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.event} - {self.player}"


class Bulletin(models.Model):
    """ Regular PDF bulletins for congresses """

    document = models.FileField(upload_to="bulletins/%Y/%m/%d/")
    create_date = models.DateTimeField(default=timezone.now)
    congress = models.ForeignKey(Congress, on_delete=models.CASCADE)
    description = models.CharField("Description", max_length=200)

    def __str__(self):
        return f"{self.congress} - {self.description}"


class CongressDownload(models.Model):
    """Documents associated with the congress that a convener wants on the
    congress page"""

    document = models.FileField(upload_to="congress-downloads/%Y/%m/%d/")
    create_date = models.DateTimeField(default=timezone.now)
    congress = models.ForeignKey(Congress, on_delete=models.CASCADE)
    description = models.CharField("Description", max_length=200)

    def __str__(self):
        return f"{self.congress} - {self.description}"


class PartnershipDesk(models.Model):
    """ Partnership Desk players looking for partners """

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    player = models.ForeignKey(User, on_delete=models.CASCADE)
    private = models.BooleanField(default=False)
    comment = models.TextField("Comment", null=True, blank=True)
    create_date = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.event} - {self.player}"
