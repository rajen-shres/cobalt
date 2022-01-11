import datetime
from decimal import Decimal

import bleach
import pytz
from django.contrib.humanize.templatetags.humanize import ordinal
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.timezone import localdate, localtime

from accounts.models import User
from cobalt.settings import (
    TIME_ZONE,
    BRIDGE_CREDITS,
    BLEACH_ALLOWED_TAGS,
    BLEACH_ALLOWED_ATTRIBUTES,
    BLEACH_ALLOWED_STYLES,
    TBA_PLAYER,
)
from organisations.models import Organisation
from payments.models import MemberTransaction
from rbac.core import rbac_user_has_role
from utils.templatetags.cobalt_tags import cobalt_credits
from utils.utils import cobalt_round

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
    ("Mixed", "Mixed"),
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

CONGRESS_TYPES = [
    ("national_gold", "National gold point"),
    ("state_championship", "State championship"),
    ("state_congress", "State congress"),
    ("club", "Club event"),
    ("club_congress", "Club congress"),
    ("other", "Other"),
]

PEOPLE_DEFAULT = """<table class="table"><tbody><tr><td><span style="font-weight: normal;">
Organiser:</span></td><td><span style="font-weight: normal;">Jane Doe</span></td>
</tr><tr><td><span style="font-weight: normal;">Phone:</span></td><td>
<span style="font-weight: normal;">040404040444</span></td></tr><tr><td>
<span style="font-weight: normal;">Email:</span></td><td><span style="font-weight: normal;">
me@club.com</span></td></tr><tr><td><span style="font-weight: normal;">
Chief Tournament Director:</span></td><td><span style="font-weight: normal;">
Alan Partridge</span></td></tr></tbody></table><p><br></p>"""


class CongressMaster(models.Model):
    """Master List of congresses. E.g. GCC. This is not an instance
    of a congress, just a list of the regular recurring ones.
    Congresses can only belong to one club at a time. Control for
    who can setup a congress as an instance of a congress master
    is handled by who is a convener for a club"""

    name = models.CharField("Congress Master Name", max_length=100)
    org = models.ForeignKey(Organisation, on_delete=models.CASCADE)

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
    youth_payment_discount_age = models.IntegerField("Cut off age", default=26)
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
    congress_type = models.CharField(
        "Congress Type", max_length=30, choices=CONGRESS_TYPES, blank=True, null=True
    )
    contact_email = models.EmailField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "Congresses"

    def __str__(self):
        return self.name

    # If the text changes, run it through bleach before saving
    def save(self, *args, **kwargs):

        if self.sponsors and getattr(self, "_sponsors_changed", True):
            self.sponsors = bleach.clean(
                self.sponsors,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        if self.latest_news and getattr(self, "_latest_news_changed", True):
            self.latest_news = bleach.clean(
                self.latest_news,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        if self.venue_transport and getattr(self, "_venue_transport_changed", True):
            self.venue_transport = bleach.clean(
                self.venue_transport,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        if self.venue_catering and getattr(self, "_venue_catering_changed", True):
            self.venue_catering = bleach.clean(
                self.venue_catering,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        if self.venue_additional_info and getattr(
            self, "_venue_additional_info_changed", True
        ):
            self.venue_additional_info = bleach.clean(
                self.venue_additional_info,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        if self.raw_html and getattr(self, "_raw_html_changed", True):
            self.raw_html = bleach.clean(
                self.raw_html,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        if self.general_info and getattr(self, "_general_info_changed", True):
            self.general_info = bleach.clean(
                self.general_info,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        if self.people and getattr(self, "_people_changed", True):
            self.people = bleach.clean(
                self.people,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        if self.links and getattr(self, "_links_changed", True):
            self.links = bleach.clean(
                self.links,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        if self.latest_news and getattr(self, "_latest_news_changed", True):
            self.latest_news = bleach.clean(
                self.latest_news,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        if self.bank_transfer_details and getattr(
            self, "_bank_transfer_details_changed", True
        ):
            self.bank_transfer_details = bleach.clean(
                self.bank_transfer_details,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        if self.cheque_details and getattr(self, "_cheque_details_changed", True):
            self.cheque_details = bleach.clean(
                self.cheque_details,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        super(Congress, self).save(*args, **kwargs)

    def user_is_convener(self, user):
        """check if a user has convener rights to this congress"""

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

    @property
    def href(self):
        """Returns an HTML link tag that can be used to go to the congress admin screen"""

        tag = reverse("events:admin_summary", kwargs={"congress_id": self.id})
        return f"<a href='{tag}' target='_blank'>{self.name}</a>"


class Event(models.Model):
    """An event within a congress"""

    congress = models.ForeignKey(Congress, on_delete=models.PROTECT)
    event_name = models.CharField("Event Name", max_length=100)
    description = models.CharField("Description", max_length=400, null=True, blank=True)
    max_entries = models.IntegerField("Maximum Entries", null=True, blank=True)
    event_type = models.CharField(
        "Event Type", max_length=14, choices=EVENT_TYPES, null=True, blank=True
    )
    # Open and close dates can be overridden at the event level
    entry_open_date = models.DateField(null=True, blank=True)
    entry_close_date = models.DateField(null=True, blank=True)
    entry_close_time = models.TimeField(null=True, blank=True)
    entry_fee = models.DecimalField("Entry Fee", max_digits=12, decimal_places=2)
    entry_early_payment_discount = models.DecimalField(
        "Early Payment Discount",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        default=Decimal(0.0),
    )
    entry_youth_payment_discount = models.IntegerField(
        "Youth Discount Percentage", default=50
    )
    player_format = models.CharField(
        "Player Format",
        max_length=14,
        choices=EVENT_PLAYER_FORMAT,
    )
    free_format_question = models.CharField(
        "Free Format Question", max_length=60, null=True, blank=True
    )
    allow_team_names = models.BooleanField(default=False)
    list_priority_order = models.IntegerField(default=0)

    def __str__(self):
        return "%s - %s" % (self.congress, self.event_name)

        # If the text changes, run it through bleach before saving

    def save(self, *args, **kwargs):

        if self.event_name and getattr(self, "_event_name_changed", True):
            self.event_name = bleach.clean(
                self.event_name,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        if self.description and getattr(self, "_description_changed", True):
            self.description = bleach.clean(
                self.description,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        if self.free_format_question and getattr(
            self, "_free_format_question_changed", True
        ):
            self.free_format_question = bleach.clean(
                self.free_format_question,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        super(Event, self).save(*args, **kwargs)

    def is_open(self):
        """check if this event is taking entries today"""

        today = localdate()
        time_now = localtime().time()

        open_date = self.entry_open_date
        if not open_date:
            open_date = self.congress.entry_open_date
        if open_date and today < open_date:
            return False

        close_date = self.entry_close_date
        if not close_date:
            close_date = self.congress.entry_close_date
        if close_date:
            if today > close_date:
                return False
            if (
                today == close_date
                and self.entry_close_time
                and self.entry_close_time < time_now
            ):
                return False

        # check start date of event
        start_date = self.start_date()

        if start_date and start_date < today:  # event started
            return False
        elif start_date == today:
            start_time = self.start_time()
            if start_time and start_time < time_now:
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
        if (
            self.congress.allow_early_payment_discount
            and self.congress.early_payment_discount_date
        ) and self.congress.early_payment_discount_date >= check_date:
            entry_fee = (
                self.entry_fee - self.entry_early_payment_discount
            ) / players_per_entry
            entry_fee = cobalt_round(entry_fee)
            reason = "Early discount"
            discount = float(self.entry_fee) / players_per_entry - float(entry_fee)
            description = "Early discount " + cobalt_credits(discount)

        # youth discounts apply after early entry discounts
        if (
            self.congress.allow_youth_payment_discount
            and self.congress.youth_payment_discount_date
        ) and user.dob:  # skip if no date of birth set
            dob = datetime.datetime.combine(user.dob, datetime.time(0, 0))
            dob = timezone.make_aware(dob, pytz.timezone(TIME_ZONE))

            # changing the year if date is 29th Feb can cause errors - change to 28th
            if dob.month == 2 and dob.day == 29:
                dob = dob.replace(day=28)

            ref_date = dob.replace(
                year=dob.year + self.congress.youth_payment_discount_age
            )
            if self.congress.youth_payment_discount_date <= ref_date.date():
                entry_fee = float(entry_fee) - (
                    float(entry_fee) * float(self.entry_youth_payment_discount) / 100.0
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
        """check if a user has already entered"""

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
        """return the start time of this event"""
        session = Session.objects.filter(event=self)
        if session:
            return session.earliest("session_date").session_start
        else:
            return None

    def start_date(self):
        """return the start date of this event"""
        session = Session.objects.filter(event=self)
        if session:
            return session.earliest("session_date").session_date
        else:
            return None

    def end_date(self):
        """return the end date of this event"""
        session = Session.objects.filter(event=self)
        if session:
            return session.latest("session_date").session_date
        else:
            return None

    def print_dates(self):
        """returns nicely formatted date string for event"""
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
        """returns the status of the team/pairs/individual entry"""

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
        """check if event is already full"""

        if self.max_entries is None:
            return False

        entries = (
            EventEntry.objects.filter(event=self)
            .exclude(entry_status="Cancelled")
            .count()
        )
        return entries >= self.max_entries

    @property
    def href(self):
        """Returns an HTML link tag that can be used to go to the event log"""

        tag = reverse("events:admin_event_log", kwargs={"event_id": self.id})
        return format_html(
            "<a href='{}' target='_blank'>{} - {}</a>",
            mark_safe(tag),
            self.congress,
            self.event_name,
        )


class Category(models.Model):
    """Event Categories such as <100 MPs or club members etc. Free format."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    description = models.CharField("Event Category", max_length=30)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.description

    def save(self, *args, **kwargs):

        if self.description and getattr(self, "_description_changed", True):
            self.description = bleach.clean(
                self.description,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        super(Category, self).save(*args, **kwargs)


class Session(models.Model):
    """A session within an event"""

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    session_date = models.DateField()
    session_start = models.TimeField()
    session_end = models.TimeField(null=True, blank=True)

    @property
    def href(self):
        """Returns an HTML link tag that can be used to go to the session edit screen"""

        tag = reverse(
            "events:edit_session",
            kwargs={"session_id": self.id, "event_id": self.event.id},
        )
        return f"<a href='{tag}' target='_blank'>{self.session_date} {self.session_start}</a>"


class EventEntry(models.Model):
    """An entry to an event"""

    event = models.ForeignKey(Event, on_delete=models.PROTECT)
    entry_status = models.CharField(
        "Entry Status", max_length=20, choices=ENTRY_STATUSES, default="Pending"
    )
    primary_entrant = models.ForeignKey(User, on_delete=models.PROTECT)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True
    )
    free_format_answer = models.CharField(
        "Free Format Answer", max_length=60, null=True, blank=True
    )
    team_name = models.CharField(max_length=15, null=True, blank=True)
    notes = models.TextField("Notes", null=True, blank=True)
    comment = models.TextField("Comments", null=True, blank=True)
    first_created_date = models.DateTimeField(default=timezone.now)
    entry_complete_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "Event entries"

    def __str__(self):
        return "%s - %s - %s" % (
            self.event.congress,
            self.event.event_name,
            self.primary_entrant,
        )

    def save(self, *args, **kwargs):

        if self.free_format_answer and getattr(
            self, "_free_format_answer_changed", True
        ):
            self.free_format_answer = bleach.clean(
                self.free_format_answer,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        if self.notes and getattr(self, "_notes_changed", True):
            self.notes = bleach.clean(
                self.notes,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        if self.comment and getattr(self, "_comment_changed", True):
            self.comment = bleach.clean(
                self.comment,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        super(EventEntry, self).save(*args, **kwargs)

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
            .exists()
        )

        return allowed

    @property
    def href(self):
        """Returns an HTML link tag that can be used to go to the event entry view"""

        tag = reverse("events:admin_evententry", kwargs={"evententry_id": self.id})
        return f"<a href='{tag}' target='_blank'>{self.event.congress} - {self.event.event_name}</a>"

    def ordered_event_entry_player(self):
        """helper function to set order of queryset for event_entry_player"""

        return self.evententryplayer_set.all().distinct("pk").order_by("pk")

    def get_team_name(self):
        """If the team name field is None we default the team name to the surname of the primary entrant.
        We also return it in uppercase and truncate to 15 chars"""

        if self.event.allow_team_names and self.team_name:
            return self.team_name.upper()

        if self.primary_entrant.id == TBA_PLAYER:
            return "TBA"
        else:
            return self.primary_entrant.last_name.upper()[:15]


class EventEntryPlayer(models.Model):
    """A player who is entering an event"""

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
    # See doco for more info, this allows a convener to enter meaningful data into the entry
    # for download to a scoring program. It is a last resort for registered players who refuse to
    # sign up for Cobalt.
    override_tba_name = models.CharField(max_length=50, null=True, blank=True)
    override_tba_system_number = models.IntegerField(default=0)
    first_created_date = models.DateTimeField(default=timezone.now)
    entry_complete_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return "%s - %s" % (self.event_entry, self.player)

    def save(self, *args, **kwargs):

        if self.reason and getattr(self, "_reason_changed", True):
            self.reason = bleach.clean(
                self.reason,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        super(EventEntryPlayer, self).save(*args, **kwargs)


class PlayerBatchId(models.Model):
    """Maps a batch Id associated with a payment to the user who made the
    payment. We use the same approach for all players so can't assume it
    will be the primary entrant."""

    player = models.ForeignKey(User, on_delete=models.CASCADE)
    batch_id = models.CharField(
        "Payment Batch ID", max_length=40, null=True, blank=True
    )


class CongressLink(models.Model):
    """Link Items for Congresses"""

    congress = models.ForeignKey(Congress, on_delete=models.CASCADE)
    link = models.CharField("Congress Link", max_length=100)

    def __str__(self):
        return "%s" % (self.congress)


class CongressNewsItem(models.Model):
    """News Items for Congresses"""

    congress = models.ForeignKey(Congress, on_delete=models.CASCADE)
    text = models.TextField()

    def __str__(self):
        return "%s" % self.congress

    def save(self, *args, **kwargs):

        if self.text and getattr(self, "_text_changed", True):
            self.text = bleach.clean(
                self.text,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        super(CongressNewsItem, self).save(*args, **kwargs)


class BasketItem(models.Model):
    """items in a basket. We don't define basket itself as it isn't needed"""

    player = models.ForeignKey(User, on_delete=models.CASCADE)
    event_entry = models.ForeignKey(EventEntry, on_delete=models.CASCADE)


class EventLog(models.Model):
    """log of things that happen within an event"""

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
    """Regular PDF bulletins for congresses"""

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
    """Partnership Desk players looking for partners"""

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    player = models.ForeignKey(User, on_delete=models.CASCADE)
    private = models.BooleanField(default=False)
    comment = models.TextField("Comment", null=True, blank=True)
    create_date = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.event} - {self.player}"

    def save(self, *args, **kwargs):

        if self.comment and getattr(self, "_comment_changed", True):
            self.comment = bleach.clean(
                self.comment,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )

        super(PartnershipDesk, self).save(*args, **kwargs)
