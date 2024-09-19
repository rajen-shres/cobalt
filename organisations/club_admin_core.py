"""
Core functions for full Club Administration (Release 6.0 and beyond)

All manipulation of the club administration related entities and attributes should be
performed through common functions in this module.

This is intended to provide some level of abstraction of the implementation of the
club administration data model so that future changes can be made more easily.

Key functions are:
    get_member_details      : get the details of a single club member
    get_club_members        : get details of a number of club members
    can_perform_action      : validate that an action can be perormed on a member
    get_valid_actions       : get a list of all valid actions that can be performed
                              on a specific member
    perform_simple_action   : perform an action on a member
"""

from datetime import date, timedelta
from itertools import chain
import logging

from django.urls import reverse
from django.utils import timezone
from django.template.loader import render_to_string

from accounts.models import (
    User,
    UnregisteredUser,
    UserAdditionalInfo,
)
from cobalt.settings import (
    BRIDGE_CREDITS,
    GLOBAL_TITLE,
    GLOBAL_ORG,
)

from utils.templatetags.cobalt_tags import cobalt_nice_date_short

from masterpoints.views import user_summary

from notifications.models import (
    BatchID,
    Recipient,
)

from payments.models import OrgPaymentMethod

from rbac.core import (
    rbac_get_users_with_role,
)

from .models import (
    ClubLog,
    ClubMemberLog,
    MembershipType,
    MemberMembershipType,
    MemberClubDetails,
    MemberClubEmail,
    MemberClubTag,
    MemberClubOptions,
    Organisation,
    OrgEmailTemplate,
    RenewalParameters,
)

from .forms import (
    BulkRenewalLineForm,
)


logger = logging.getLogger("cobalt")


# -------------------------------------------------------------------------------------
# Exceptions
# Used to shield the consuming code from data model specific exceptions
# -------------------------------------------------------------------------------------


class CobaltMemberNotFound(Exception):
    """A member could not be found"""

    def __init__(self, club, system_number):
        if club:
            message = f"No member in {club} with number {system_number}"
        else:
            message = f"No member with number {system_number}"
        super().__init__(message)


# -------------------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------------------


# membership states/statuses which end a membership
MEMBERSHIP_STATES_TERMINAL = [
    MemberMembershipType.MEMBERSHIP_STATE_LAPSED,
    MemberMembershipType.MEMBERSHIP_STATE_RESIGNED,
    MemberMembershipType.MEMBERSHIP_STATE_TERMINATED,
    MemberMembershipType.MEMBERSHIP_STATE_DECEASED,
]

# membership states/statuses which represent an active membership
MEMBERSHIP_STATES_ACTIVE = [
    MemberMembershipType.MEMBERSHIP_STATE_CURRENT,
    MemberMembershipType.MEMBERSHIP_STATE_DUE,
]

# membership states/statuses which represent memberships that should never be used
MEMBERSHIP_STATES_DO_NOT_USE = [
    MemberMembershipType.MEMBERSHIP_STATE_DECEASED,
]


# -------------------------------------------------------------------------------------
# Utility Functions
# -------------------------------------------------------------------------------------


def log_member_change(club, system_number, actor, description):
    """Log a change to a club member

    Args:
        club (Organisation): the club
        system_number (int): the member's system number
        actor (User): the User making the change or None if a system generated change
        description (string): a description of the change
    """
    ClubMemberLog(
        club=club,
        system_number=system_number,
        actor=actor,
        description=description,
    ).save()


def get_member_log(club, system_number):
    """Log the log records fora club member

    Args:
        club (Organisation): the club
        system_number (int): the member's system number

    Returns:
        QuerySet: the log records for this member in reverse chronological order
    """

    return ClubMemberLog.objects.filter(
        club=club,
        system_number=system_number,
    ).select_related("actor")


def description_for_status(status):
    """Returns the human readable descrption of a membership status (or state)
    Note: this is only required when using membershiop status codes outside of
    an attribute (when <object>.get_FOO_display) can be used instead.

    Args:
        status (MemberClubDetails.MEMBERSHIP_STATUS): the status (or state)

    Returns:
        str: Description
    """

    membership_status_dict = dict(MemberClubDetails.MEMBERSHIP_STATUS)
    return membership_status_dict.get(status, "Unknown Status")


def member_has_future(club, system_number):
    """Does the member have a future dated membership?"""

    return (
        MemberMembershipType.objects.filter(
            membership_type__organisation=club,
            system_number=system_number,
            membership_state=MemberMembershipType.MEMBERSHIP_STATE_FUTURE,
        ).count()
        > 0
    )


def member_details_short_description(member_details):
    """A brief description of the membership status"""

    if member_details.membership_status in MEMBERSHIP_STATES_ACTIVE:
        desc = f"Current membership: {member_details.latest_membership.membership_type.name}"
    else:
        desc = (
            f"{member_details.get_membership_status_display()} membership: "
            f"{member_details.latest_membership.membership_type.name}"
        )

    latest_paid_until = member_details.latest_paid_until_date
    if latest_paid_until:
        desc += f", paid until {cobalt_nice_date_short(latest_paid_until)}"

    os_fees = member_details.outstanding_fees
    if os_fees > 0:
        desc += f", {os_fees} membership fees to pay"

    return desc


def member_details_description(member_details):
    """A comprehensive descriptive string of the type, status and relevant dates"""

    contiguous_start, contiguous_end = member_details.current_type_dates

    period = f"from {contiguous_start:%d %b %Y}"
    if contiguous_end:
        period += f" to {contiguous_end:%d %b %Y}"

    joined_and_left = (
        f"Joined {member_details.joined_date:%d %b %Y}"
        if member_details.joined_date
        else None
    )
    if member_details.left_date:
        if joined_and_left:
            joined_and_left += f", left {member_details.left_date:%d %b %Y}. "
        else:
            joined_and_left += f"Left {member_details.left_date:%d %b %Y}. "
    elif joined_and_left:
        joined_and_left += ". "

    #  get the furthest future future membership (if any)
    future_membership = (
        MemberMembershipType.objects.filter(
            membership_type__organisation=member_details.club,
            system_number=member_details.system_number,
            membership_state=MemberMembershipType.MEMBERSHIP_STATE_FUTURE,
        )
        .order_by("end_date")
        .last()
    )

    paid_until = None
    if future_membership and future_membership.is_paid and future_membership.end_date:
        paid_until = (
            f"paid until {member_details.future_membership.paid_until_date:%d %b %Y}"
        )

    elif (
        member_details.latest_membership.is_paid
        and member_details.latest_membership.end_date
    ):
        paid_until = (
            f"paid until {member_details.latest_membership.paid_until_date:%d %b %Y}"
        )

    if member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_CURRENT:
        desc = (
            f"{member_details.latest_membership.membership_type.name} member, {period}"
        )
        if paid_until:
            desc += f", {paid_until}"

        if not member_details.latest_membership.is_paid:
            desc += f", {member_details.latest_membership.fee} due {member_details.latest_membership.due_date:%d %b %Y}"
        desc += f". {joined_and_left}"
    elif member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_DUE:
        desc = f"{member_details.latest_membership.membership_type.name} member, {period}, "
        if paid_until:
            desc += f"{paid_until}, "
        desc += (
            f"{member_details.latest_membership.fee} due {member_details.latest_membership.due_date:%d %b %Y}"
            f". {joined_and_left}"
        )
    else:
        desc = (
            f"{member_details.get_membership_status_display()}. {joined_and_left}"
            f"{member_details.latest_membership.membership_type.name} membership {period}"
        )
        if paid_until:
            desc += f", {paid_until}"

    return desc


def get_membership_details_for_club(club, exclude_id=None):
    """Return a membership type details for this club, for use by JavaScript in
    defaulting fields driven by membership type.

    Args:
        club (Organisation): the club
        exclude_id (int): a membership type id to exclude (eg the current one)

    Returns:
        list: membership choices list (tuples of id and name), with values
                in a form that JavaScript can ingest.
        dict: membership details keyed by membership type id
    """

    membership_types = MembershipType.objects.filter(organisation=club)
    if exclude_id:
        membership_types = membership_types.exclude(id=exclude_id)
    membership_types = membership_types.all()

    membership_choices = [(mt.id, mt.name) for mt in membership_types]

    today = timezone.now().date()
    fees_and_due_dates = {
        f"{mt.id}": {
            "annual_fee": str(float(mt.annual_fee))
            if club.full_club_admin and mt.annual_fee
            else "0",
            "due_date": (today + timedelta(mt.grace_period_days)).strftime("%d/%m/%Y"),
            "end_date": ""
            if mt.does_not_renew
            else club.current_end_date.strftime("%d/%m/%Y"),
            "perpetual": "Y" if mt.does_not_renew else "N",
        }
        for mt in membership_types
    }

    return (membership_choices, fees_and_due_dates)


# -------------------------------------------------------------------------------------
#   Data accessor functions
#
#   Key functions for accessing membership data are:
#       get_member_details : get a single member's details
#       get_club_members : get all club members
# -------------------------------------------------------------------------------------


def get_club_options_for_user(user):
    """Return a query set of member club option records for a user

    Checks that records exist for all club memberships for the user,
    and creates any missing records with the default values.
    Adds the current membership_status (or None) to each option record

    Args:
        user (User): the registered user

    Returns:
        list: list of MemberClubOptions, ordered by club name
    """

    # get existing options records, and build a dictionary keyed on club

    club_options_qs = (
        MemberClubOptions.objects.filter(
            user=user,
        )
        .select_related("club")
        .order_by("club__name")
    )

    club_options = []
    for option in club_options_qs:
        option.membership_status = None
        club_options.append(option)

    options_dict = {club_option.club: club_option for club_option in club_options}

    # get all memberships for this user and fill in any missing options

    memberships = (
        MemberClubDetails.objects.filter(
            system_number=user.system_number,
        )
        .exclude(
            membership_status=MemberClubDetails.MEMBERSHIP_STATUS_CONTACT,
        )
        .select_related("club")
    )

    for membership in memberships:
        if membership.club not in options_dict:
            missing_options = MemberClubOptions(
                club=membership.club,
                user=user,
            )
            missing_options.save()
            missing_options.membership_status = (
                membership.get_membership_status_display()
            )
            club_options.append(missing_options)
            options_dict[membership.club] = missing_options
        else:
            options_dict[
                membership.club
            ].membership_status = membership.get_membership_status_display()

    return club_options


def is_player_allowing_club_membership(club, system_number):
    """Checks whether this user is blocking membership for this club

    Creates a default options record if none exists
    """

    try:
        user = User.objects.get(system_number=system_number)
    except User.DoesNotExist:
        # No restrictions for unregistered users
        return True

    club_options = MemberClubOptions.objects.filter(
        club=club,
        user=user,
    ).last()

    if not club_options:
        club_options = MemberClubOptions(
            club=club,
            user=user,
        )
        club_options.save()

    return club_options.allow_membership


def get_membership_type(club, system_number):
    """Get the current membership type for a member in a club

    Returns None if not an active member of the club"""

    member_details = (
        MemberClubDetails.objects.filter(
            club=club,
            system_number=system_number,
        )
        .select_related("latest_membership")
        .last()
    )

    if not member_details:
        return None

    if member_details.membership_status not in MEMBERSHIP_STATES_ACTIVE:
        return None

    return member_details.latest_membership


def is_player_a_member(club, system_number):
    """Is the player a current active member?"""

    return get_membership_type(club, system_number) is not None


def get_membership_type_for_players(club, system_number_list):
    """Returns the current, active membership type for a list of system_numbers.

    Args:
        club (Organisation_: the club)
        system_number_list (list): list of system numbers

    Returns:
        dict: system_number => membership type name (str)

    Only members found will be in the dictionary.
    """

    membership_types = MemberMembershipType.objects.filter(
        system_number__in=system_number_list,
        membership_state__in=MEMBERSHIP_STATES_ACTIVE,
        membership_type__organisation=club,
    ).select_related("membership_type")

    return {
        membership_type.system_number: membership_type.membership_type.name
        for membership_type in membership_types
    }


def get_member_details(club, system_number):
    """Return a MemberClubDetails object augmented with user/unregistered user information

    Args:
        club (Organisation): the club
        system_number (int): the member's system_number

    Returns:
        object: augmented MemberClubDetails or None
    """

    member_qs = MemberClubDetails.objects.filter(
        club=club,
        system_number=system_number,
    )

    augmented_list = _augment_member_details(member_qs, None)

    if len(augmented_list) == 0:
        return None
    else:
        return augmented_list[0]


def check_user_or_unreg_deceased(system_number):
    """Checks whether a user or unregistered user is marked as deceased at the user level
    (ie marked by the support function, not by a club)

    Args:
        system_number: the member's system_number

    Returns:
        bool: is deceased

    Raises:
        CobaltMemberNotFound: if no record found with this system number
    """

    user = User.objects.filter(system_number=system_number).last()

    if user:
        return user.deceased
    else:
        unreg_user = UnregisteredUser.objects.filter(system_number=system_number).last()
        if unreg_user:
            return unreg_user.deceased
        else:
            raise CobaltMemberNotFound(None, system_number)


def get_member_count(club, reference_date=None):
    """Get member count for club with optional as at date"""

    if not reference_date:
        # just return the current membership

        return MemberClubDetails.objects.filter(
            club=club, membership_status__in=MEMBERSHIP_STATES_ACTIVE
        ).count()

    # asking for membership count at a specific date
    # so look at the members - membership records

    # not clear this will always be accurate, eg if a person
    # resigns part way through a membership period.

    non_renewing_count = MemberMembershipType.objects.filter(
        membership_type__organisation=club,
        start_date__lte=reference_date,
        end_date=None,
    ).count()

    renewing_count = (
        MemberMembershipType.objects.filter(
            membership_type__organisation=club,
            start_date__lte=reference_date,
        )
        .exclude(
            end_date=None,
        )
        .filter(end_date__gte=reference_date)
        .count()
    )

    return non_renewing_count + renewing_count


def club_has_unregistered_members(club):
    """Returns whether a club has any current unregistered members"""

    members = MemberClubDetails.objects.filter(
        club=club, membership_status__in=MEMBERSHIP_STATES_ACTIVE
    ).values("system_number")

    return (
        UnregisteredUser.objects.filter(system_number__in=members)
        .exclude(
            deceased=True,
        )
        .exists()
    )


def get_member_system_numbers(club, target_list=None, get_all=False):
    """Return a list of system numbers for members,
    optionally constrained within a list of system numbers.
    By default only current members are included

    Args:
        club (Organisation): the club
        target_list (list): system numbers to narrow the query
        get_all (bool): include non current members? Defaults False
    """

    qs = MemberClubDetails.objects.filter(
        club=club,
    )

    if get_all:
        qs = qs.exclude(membership_status=MemberClubDetails.MEMBERSHIP_STATUS_CONTACT)
    else:
        qs = qs.filter(membership_status__in=MEMBERSHIP_STATES_ACTIVE)

    if target_list:
        qs = qs.filter(system_number__in=target_list)

    return qs.values_list("system_number", flat=True)


def get_contact_system_numbers(club, target_list=None):
    """Return a list of system numbers for club contacts,
    optionally constarined within a list of system numbers

    Args:
        club (Organisation): the club
        target_list (list): system numbers to narrow the query
    """

    qs = MemberClubDetails.objects.filter(
        club=club,
        membership_status=MemberClubDetails.MEMBERSHIP_STATUS_CONTACT,
    )

    if target_list:
        qs = qs.filter(system_number__in=target_list)

    return qs.values_list("system_number", flat=True)


def get_club_members(
    club,
    sort_option="last_desc",
    active_only=True,
    exclude_contacts=True,
    exclude_deceased=True,
):
    """Returns a list of member detail objects for the specified club,
    augmented with:
        first_name (str): First name
        last_name (str): Last name
        user_type (str): '{GLOBAL_TITLE} User' | 'Unregistered User'
        user_or_unreg_id (int): pk to either User or UnregisteredUser
        club_email (str or None): the email to use for club purposes
        internal (bool): is the system number an internal one?

    Args:
        club (Organisation): the club
        sort_option (string): sort column and order
        exclude_contacts (boolean): exclude contacts from the list
        active_only (boolean): include only current and due members

    Returns:
        list: augmented club member details in the specified order
    """

    members = MemberClubDetails.objects.filter(club=club)

    # Note: status should never be future, but included here to cater
    # for simplified membership management where anything goes

    if active_only:
        members = members.filter(
            membership_status__in=[
                MemberClubDetails.MEMBERSHIP_STATUS_CURRENT,
                MemberClubDetails.MEMBERSHIP_STATUS_DUE,
                MemberClubDetails.MEMBERSHIP_STATUS_CONTACT,
                MemberClubDetails.MEMBERSHIP_STATUS_FUTURE,
            ]
        )

    if exclude_contacts:
        members = members.exclude(
            membership_status=MemberClubDetails.MEMBERSHIP_STATUS_CONTACT
        )

    if exclude_deceased:
        members = members.exclude(
            membership_status=MemberClubDetails.MEMBERSHIP_STATUS_DECEASED
        )

    members = members.select_related("latest_membership__membership_type")

    # augment with additional details
    return _augment_member_details(members, sort_option=sort_option)


def _augment_member_details(member_qs, sort_option="last_desc"):
    """Augments a query set of members with user/unregistered user details

    The attributes added are:
        first_name (str): First name
        last_name (str): Last name
        user_type (str): '{GLOBAL_TITLE} User' | 'Unregistered User'
        user_or_unreg_id (int): pk to either User or UnregisteredUser
        club_email (str or None): the email to use for club purposes
        internal (bool): is the system number an internal one?

    Args:
        club (Organisation): the club to which these members belong
        member_qs (MemberClubDetails QuerySet): the selected members
        sort_option (string): sort column and order

    Returns:
        list: augmented club member details in the specified order
    """

    members = list(member_qs)
    system_numbers = [member.system_number for member in members]

    users = User.objects.filter(system_number__in=system_numbers)
    unreg_users = UnregisteredUser.all_objects.filter(system_number__in=system_numbers)
    player_dict = {
        player.system_number: {
            "first_name": player.first_name,
            "last_name": player.last_name,
            "user_type": f"{GLOBAL_TITLE} User"
            if type(player) is User
            else "Unregistered User",
            "user_or_unreg_id": player.id,
            "user_or_unreg": player,
            "user_email": player.email if type(player) is User else None,
            "internal": False
            if type(player) is User
            else player.internal_system_number,
        }
        for player in chain(users, unreg_users)
    }

    for member in members:
        if member.system_number in player_dict:
            member.first_name = player_dict[member.system_number]["first_name"]
            member.last_name = player_dict[member.system_number]["last_name"]
            member.user_type = player_dict[member.system_number]["user_type"]
            member.user_or_unreg_id = player_dict[member.system_number][
                "user_or_unreg_id"
            ]
            member.user_or_unreg = player_dict[member.system_number]["user_or_unreg"]
            member.internal = player_dict[member.system_number]["internal"]

            # Note: this needs to replicate the logic in club_email_for_member
            if member.email:
                member.club_email = member.email
            else:
                if (
                    member.membership_status
                    == MemberClubDetails.MEMBERSHIP_STATUS_CONTACT
                    or member.membership_status
                    == MemberClubDetails.MEMBERSHIP_STATUS_DECEASED
                ):
                    member.club_email = None
                else:
                    member.club_email = player_dict[member.system_number]["user_email"]
        else:
            member.first_name = "Unknown"
            member.last_name = "Unknown"
            member.user_type = "Unknown Type"
            member.user_or_unreg_id = None
            member.club_email = None
            member.internal = True

    # sort
    if sort_option == "first_desc":
        members.sort(key=lambda x: x.first_name.lower())
    elif sort_option == "first_asc":
        members.sort(key=lambda x: x.first_name.lower(), reverse=True)
    elif sort_option == "last_desc":
        members.sort(key=lambda x: (x.last_name.lower(), x.first_name.lower()))
    elif sort_option == "last_asc":
        members.sort(
            key=lambda x: (x.last_name.lower(), x.first_name.lower()), reverse=True
        )
    elif sort_option == "system_number_desc":
        members.sort(key=lambda x: x.system_number)
    elif sort_option == "system_number_asc":
        members.sort(key=lambda x: x.system_number, reverse=True)
    elif sort_option == "membership_desc":
        members.sort(
            key=lambda x: (
                x.latest_membership.membership_type.name,
                x.last_name.lower(),
                x.first_name.lower(),
            )
        )
    elif sort_option == "membership_asc":
        members.sort(key=lambda x: (x.last_name.lower(), x.first_name.lower()))
        members.sort(
            key=lambda x: x.latest_membership.membership_type.name, reverse=True
        )
    elif sort_option == "home_desc":
        members.sort(key=lambda x: (x.last_name.lower(), x.first_name.lower()))
        members.sort(key=lambda x: x.latest_membership.home_club, reverse=True)
    elif sort_option == "home_asc":
        members.sort(
            key=lambda x: (
                x.latest_membership.home_club,
                x.last_name.lower(),
                x.first_name.lower(),
            )
        )
    elif sort_option == "status_desc":
        members.sort(
            key=lambda x: (
                x.membership_status,
                x.last_name.lower(),
                x.first_name.lower(),
            )
        )
    elif sort_option == "status_asc":
        members.sort(key=lambda x: (x.last_name.lower(), x.first_name.lower()))
        members.sort(key=lambda x: x.membership_status, reverse=True)
    elif sort_option == "type_desc":
        members.sort(
            key=lambda x: (x.user_type, x.last_name.lower(), x.first_name.lower())
        )
    elif sort_option == "type_asc":
        members.sort(key=lambda x: (x.last_name.lower(), x.first_name.lower()))
        members.sort(key=lambda x: x.user_type, reverse=True)

    return members


def get_club_member_list(
    club,
    active_only=True,
    exclude_contacts=True,
    exclude_deceased=True,
):
    """Return a list of system numbers of club members"""

    members = MemberClubDetails.objects.filter(club=club)

    if active_only:
        members = members.filter(
            membership_status__in=[
                MemberClubDetails.MEMBERSHIP_STATUS_CURRENT,
                MemberClubDetails.MEMBERSHIP_STATUS_DUE,
                MemberClubDetails.MEMBERSHIP_STATUS_CONTACT,
            ]
        )

    if exclude_contacts:
        members = members.exclude(
            membership_status=MemberClubDetails.MEMBERSHIP_STATUS_CONTACT
        )

    if exclude_deceased:
        members = members.exclude(
            membership_status=MemberClubDetails.MEMBERSHIP_STATUS_DECEASED
        )

    return members.values_list("system_number", flat=True)


def get_club_member_list_email_match(
    club,
    search_str,
    active_only=True,
    exclude_contacts=True,
    exclude_deceased=True,
    strict_match=False,
):
    """Return a list of member's system numbers, matching on email address



    Note that this only searches on the member's email, not the email in the user record"""

    members = MemberClubDetails.objects.filter(club=club)

    if active_only:
        members = members.filter(
            membership_status__in=[
                MemberClubDetails.MEMBERSHIP_STATUS_CURRENT,
                MemberClubDetails.MEMBERSHIP_STATUS_DUE,
                MemberClubDetails.MEMBERSHIP_STATUS_CONTACT,
            ]
        )

    if exclude_contacts:
        members = members.exclude(
            membership_status=MemberClubDetails.MEMBERSHIP_STATUS_CONTACT
        )

    if exclude_deceased:
        members = members.exclude(
            membership_status=MemberClubDetails.MEMBERSHIP_STATUS_DECEASED
        )

    if strict_match:
        members = members.filter(email=search_str)
    else:
        members = members.filter(email__icontains=search_str)

    return members.values_list("system_number", flat=True)


def get_club_member_list_for_emails(
    club,
    email_list,
    active_only=True,
    exclude_contacts=True,
    exclude_deceased=True,
):
    """Return a list of member's system numbers to emails, matching a list of emails

    Args:
        club (Organisation): the club or None for all clubs
        email_list (list): list of email addresses

    Returns:
        list: list of (system numbers, email)

    Note that this only searches on the member's email, not the email in the user record"""

    members = MemberClubDetails.objects

    if club:
        members = members.filter(club=club)

    if active_only:
        members = members.filter(
            membership_status__in=[
                MemberClubDetails.MEMBERSHIP_STATUS_CURRENT,
                MemberClubDetails.MEMBERSHIP_STATUS_DUE,
                MemberClubDetails.MEMBERSHIP_STATUS_CONTACT,
            ]
        )

    if exclude_contacts:
        members = members.exclude(
            membership_status=MemberClubDetails.MEMBERSHIP_STATUS_CONTACT
        )

    if exclude_deceased:
        members = members.exclude(
            membership_status=MemberClubDetails.MEMBERSHIP_STATUS_DECEASED
        )

    members = members.filter(email__in=email_list)

    return members.values_list("system_number", "email")


def get_club_emails_for_system_number(system_number):
    """Returns a list of club emails associated with this system number across clubs"""

    return MemberClubDetails.objects.filter(
        system_number=system_number, email=True
    ).values_list("email", flat=True)


def get_club_contact_list(
    club,
):
    """Return a list of system numbers of club contacts"""

    return MemberClubDetails.objects.filter(
        club=club,
        membership_status=MemberClubDetails.MEMBERSHIP_STATUS_CONTACT,
    ).values_list("system_number", flat=True)


def get_club_contact_list_email_match(
    club,
    search_str,
    strict_match=False,
):
    """Return a list of system numbers of club contacts, matching on email address

    Note that this only searches on the member's email, not the email in the user record"""

    qs = MemberClubDetails.objects.filter(
        club=club,
        membership_status=MemberClubDetails.MEMBERSHIP_STATUS_CONTACT,
    )

    if strict_match:
        qs = qs.filter(email=search_str)
    else:
        qs = qs.filter(email__icontains=search_str)

    return qs.values_list("system_number", flat=True)


def get_club_contacts(
    club,
    sort_option="last_desc",
):
    """Returns a list of contact detail objects for the specified club, augmented with
    the names and types (user, unregistered, contact).

    Args:
        club (Organisation): the club
        sort_option (string): sort column and order

    Returns:
        list: augmented club member details in the specified order
    """

    contacts = MemberClubDetails.objects.filter(
        club=club,
        membership_status=MemberClubDetails.MEMBERSHIP_STATUS_CONTACT,
    )

    # augment with additional details
    return _augment_contact_details(club, contacts, sort_option=sort_option)


def _augment_contact_details(club, contact_qs, sort_option="last_desc"):
    """Augments a query set of contacts with user/unregistered user details

    Args:
        club (Organisation): the club to which these members belong
        member_qs (MemberClubDetails QuerySet): the selected members
        sort_option (string): sort column and order

    Returns:
        list: augmented club member details in the specified order
    """

    contacts = list(contact_qs)
    system_numbers = [contact.system_number for contact in contacts]

    users = User.objects.filter(system_number__in=system_numbers)
    unreg_users = UnregisteredUser.all_objects.filter(system_number__in=system_numbers)

    # get system numbers of registered users blocking membership of this club
    blocking_system_numbers = MemberClubOptions.objects.filter(
        club=club,
        user__in=users,
        allow_membership=False,
    ).values_list("user__system_number", flat=True)

    player_dict = {
        player.system_number: {
            "first_name": player.first_name,
            "last_name": player.last_name,
            "user_type": f"{GLOBAL_TITLE} User"
            if type(player) is User
            else (
                "Contact Only" if player.internal_system_number else "Unregistered User"
            ),
            "user_or_unreg_id": player.id,
            "internal": False
            if type(player) is User
            else player.internal_system_number,
            "blocking_membership": player.system_number in blocking_system_numbers,
        }
        for player in chain(users, unreg_users)
    }

    for contact in contacts:
        if contact.system_number in player_dict:
            contact.first_name = player_dict[contact.system_number]["first_name"]
            contact.last_name = player_dict[contact.system_number]["last_name"]
            contact.user_type = player_dict[contact.system_number]["user_type"]
            contact.user_or_unreg_id = player_dict[contact.system_number][
                "user_or_unreg_id"
            ]
            contact.internal = player_dict[contact.system_number]["internal"]
            # Note: only ever use the contact email for a contact (ie don't use User email)
            contact.club_email = contact.email
            contact.blocking_membership = player_dict[contact.system_number][
                "blocking_membership"
            ]
        else:
            contact.first_name = "Unknown"
            contact.last_name = "Unknown"
            contact.user_type = "Unknown Type"
            contact.user_or_unreg_id = None
            contact.internal = True
            contact.club_email = contact.email
            contact.blocking_membership = True

    # sort
    if sort_option == "first_desc":
        contacts.sort(key=lambda x: x.first_name.lower())
    elif sort_option == "first_asc":
        contacts.sort(key=lambda x: x.first_name.lower(), reverse=True)
    elif sort_option == "last_desc":
        contacts.sort(key=lambda x: (x.last_name.lower(), x.first_name.lower()))
    elif sort_option == "last_asc":
        contacts.sort(
            key=lambda x: (x.last_name.lower(), x.first_name.lower()), reverse=True
        )
    elif sort_option == "system_number_desc":
        contacts.sort(key=lambda x: x.system_number)
    elif sort_option == "system_number_asc":
        contacts.sort(key=lambda x: x.system_number, reverse=True)

    return contacts


def get_contact_details(club, system_number):
    """Return a MemberClubDetails object augmented with user/unregistered user information

    Args:
        club (Organisation): the club
        system_number (int): the member's system_number

    Returns:
        object: augmented MemberClubDetails or None
    """

    member_qs = MemberClubDetails.objects.filter(
        club=club,
        system_number=system_number,
        membership_status=MemberClubDetails.MEMBERSHIP_STATUS_CONTACT,
    )

    augmented_list = _augment_contact_details(club, member_qs, None)

    if len(augmented_list) == 0:
        return None
    else:
        return augmented_list[0]


def club_email_for_member(club, system_number):
    """Return an email address to be used by a club for a member (or None).
    The email could be club specific or from the user record.
    No email address will be returned for a deceased member. A User level email
    will not be returned for a contact with no club specific email.

    Args:
        club (Organisation): the club
        system_number (int): member's system number

    Returns:
        string: email address or None if not specified
    """

    # get the membership details, if any
    member_details = (
        MemberClubDetails.objects.filter(
            club=club,
            system_number=system_number,
        )
        .exclude(membership_status=MemberClubDetails.MEMBERSHIP_STATUS_DECEASED)
        .last()
    )

    if not member_details:
        # not a member
        return None

    if member_details.email:
        return member_details.email

    if member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_CONTACT:
        # a contact, but no email (!), so don't look for a User record
        return None

    # no club specific email, so check for a user record
    try:
        user = User.objects.get(system_number=system_number)
    except User.DoesNotExist:
        return None

    return user.email


def has_club_email_bounced(email):
    """Checks for any club email reference to this email which has bounced

    Args:
        email (str): an email address

    Returns:
        bool: has the email bounced (for any member or contact)
    """

    return MemberClubDetails.objects.filter(
        email=email,
        email_hard_bounce=True,
    ).exists()


def set_club_email_bounced(email, email_hard_bounce_reason, email_hard_bounce_date):
    """Set bounce information for all occurances of a club email address"""

    MemberClubDetails.objects.filter(email=email,).update(
        email_hard_bounce=True,
        email_hard_bounce_reason=email_hard_bounce_reason,
        email_hard_bounce_date=email_hard_bounce_date,
    )


def clear_club_email_bounced(email):
    """Clear bounce information for all occurances of a club email address"""

    MemberClubDetails.objects.filter(email=email,).update(
        email_hard_bounce=False,
        email_hard_bounce_reason=None,
        email_hard_bounce_date=None,
    )


def get_club_memberships_for_person(system_number):
    """Return active membership details records for this user

    Args:
        system_number (int): the member's system number
    """

    return MemberClubDetails.objects.filter(
        system_number=system_number,
        membership_status__in=MEMBERSHIP_STATES_ACTIVE,
    )


def get_outstanding_membership_fees_for_user(user):
    """Return club memberships (MemberMembershipType objects) with outstanding
    fees for the user. Only returns those with an active state (current, future, due)
    and for clubs using full membership management

    Args:
        user (User): the user to check for

    Returns:
        QuerySet : query set of MemberMembershipType objects
    """

    return MemberMembershipType.objects.filter(
        system_number=user.system_number,
        fee__gt=0,
        is_paid=False,
        membership_state__in=[
            MemberMembershipType.MEMBERSHIP_STATE_CURRENT,
            MemberMembershipType.MEMBERSHIP_STATE_DUE,
            MemberMembershipType.MEMBERSHIP_STATE_FUTURE,
        ],
        membership_type__organisation__full_club_admin=True,
    ).select_related("membership_type", "membership_type__organisation")


def user_has_outstanding_membership_fees(user):
    """Checks whether a user has any outstanding membership payments"""

    return get_outstanding_membership_fees_for_user(user).count() > 0


def get_count_for_membership_type(membership_type, active_only=True):
    """Return the number of members of the given type for the club,
    either current members only or all states

    Args:
        membership_type (MembershipType): the type in question

    Returns:
        int: number of active club members of this type
    """

    qs = MemberMembershipType.objects.filter(
        membership_type=membership_type,
    )

    if active_only:
        qs = qs.filter(
            membership_state__in=[
                MemberMembershipType.MEMBERSHIP_STATE_CURRENT,
                MemberMembershipType.MEMBERSHIP_STATE_DUE,
            ]
        )

    return qs.count()


# -------------------------------------------------------------------------------------
#   Status validation functions
#
#   Single points for implementing business logic to validate whether an action can be
#   performed on a member. Should be used by the UI to ensure that options are being
#   presented consistently across teh UI and consistent with the backend.
#
#   In general consuming code should use either:
#       can_perform_action(<action name>, <member detail>), or
#       get_valid_actions(<member detail>)
#
#   All functinos have a common structure, taking a MemberClubDetails object as returned by
#   get_member_details and returning a tuple of:
#       boolean : can teh action be peroformed
#       str: an explanatory message if not valid, otherwise None
#
#   To add a new action:
#       - create a validation function
#       - add the name to MEMBER_ACTIONS
#       - add the functon to ACTION_VALIDATORS
#       - update the action function section below
#
# -------------------------------------------------------------------------------------


def can_mark_as_lapsed(member_details):
    """Can the member validly be marked as lapsed?"""

    if member_has_future(member_details.club, member_details.system_number):
        return (False, "Member has a future dated membership")

    if member_details.is_active_status:
        return (True, None)

    return (False, "Member must be in an active status to mark as lapsed")


def can_mark_as_resigned(member_details):
    """Can the member validly be marked as resigned?"""

    if member_has_future(member_details.club, member_details.system_number):
        return (False, "Member has a future dated membership")

    if (
        member_details.is_active_status
        or member_details.membership_status
        == MemberClubDetails.MEMBERSHIP_STATUS_LAPSED
    ):
        return (True, None)

    return (False, "Member must be in an active status to mark as resigned")


def can_mark_as_terminated(member_details):
    """Can the member validly be marked as terminated?"""

    if member_has_future(member_details.club, member_details.system_number):
        return (False, "Member has a future dated membership")

    if (
        member_details.is_active_status
        or member_details.membership_status
        == MemberClubDetails.MEMBERSHIP_STATUS_LAPSED
        or member_details.membership_status
        == MemberClubDetails.MEMBERSHIP_STATUS_RESIGNED
    ):
        return (True, None)

    return (False, "Member is not in a valid state to mark as terminated")


def can_mark_as_deceased(member_details):
    """Can the member validly be marked as deceased?"""

    if member_has_future(member_details.club, member_details.system_number):
        return (False, "Member has a future dated membership")

    if member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_DECEASED:
        return (False, "Member is already marked as deceased")

    if member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_CONTACT:
        return (False, "Contacts cannot be marked as deceased")

    return (True, None)


# JPG clean-up. Replaced by augmented version
def get_outstanding_memberships_for_member(club, system_number):
    """Return all memberships with outstanding fees to pay"""

    return MemberMembershipType.objects.filter(
        membership_type__organisation=club,
        system_number=system_number,
        is_paid=False,
        fee__gte=0,
        membership_state__in=[
            MemberMembershipType.MEMBERSHIP_STATE_CURRENT,
            MemberMembershipType.MEMBERSHIP_STATE_FUTURE,
            MemberMembershipType.MEMBERSHIP_STATE_DUE,
        ],
    ).order_by("start_date")


def can_mark_as_paid(member_details):
    """Can the member validly be marked as paid?"""

    os_memberships = get_outstanding_memberships_for_member(
        member_details.club, member_details.system_number
    )

    if os_memberships.count() > 0:
        return (True, None)
    else:
        return (False, "No outstanding membership fees able to be paid")


def can_extend_membership(member_details):
    """Can the member validly be extended?"""

    if member_has_future(member_details.club, member_details.system_number):
        return (False, "Member already has a future dated membership")

    if member_details.membership_status in [
        MemberClubDetails.MEMBERSHIP_STATUS_CURRENT,
        MemberClubDetails.MEMBERSHIP_STATUS_DUE,
    ]:
        if member_details.latest_membership.membership_type.does_not_renew:
            return (
                False,
                f"{member_details.latest_membership.membership_type.name} memberships do not renew",
            )
        else:
            return (True, None)

    return (False, "Member must in a current member to extend")


def can_change_membership(member_details):
    """Can the membership type of the member validly be changed?"""

    if member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_DECEASED:
        return (False, "Deceased members cannot be changed")

    if member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_CONTACT:
        return (False, "Contacts do not have memberships")

    if member_has_future(member_details.club, member_details.system_number):
        return (False, "Member already has a future dated membership")

    return (True, None)


def can_reinstate_membership(member_details):
    """Can the membership type of the member validly be reinstated?"""

    if member_details.membership_status in [
        MemberClubDetails.MEMBERSHIP_STATUS_LAPSED,
        MemberClubDetails.MEMBERSHIP_STATUS_RESIGNED,
        MemberClubDetails.MEMBERSHIP_STATUS_TERMINATED,
        MemberClubDetails.MEMBERSHIP_STATUS_DECEASED,
    ]:
        if member_details.previous_membership_status:
            return (True, None)
        else:
            return (False, "No previous status to reinstate")

    return (False, "Member is not in a valid state to reinstate a previous state")


def can_delete_member(member_details):
    """Can the membership validly be deleted?"""

    if member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_CONTACT:
        return (False, "Contacts must be deleted using Delete Contact")

    return (True, None)


# The actions that can be performed on a member/membership
MEMBER_ACTIONS = [
    "lapsed",
    "resigned",
    "terminated",
    "deceased",
    "paid",
    "extend",
    "change",
    "reinstate",
    "delete",
]


# The state validation functions for each action
ACTION_VALIDATORS = {
    "lapsed": can_mark_as_lapsed,
    "resigned": can_mark_as_resigned,
    "terminated": can_mark_as_terminated,
    "deceased": can_mark_as_deceased,
    "paid": can_mark_as_paid,
    "extend": can_extend_membership,
    "change": can_change_membership,
    "reinstate": can_reinstate_membership,
    "delete": can_delete_member,
}


def can_perform_action(action, member_details):
    """Convenience function to access the action validators"""
    if action in ACTION_VALIDATORS:
        return ACTION_VALIDATORS[action](member_details)
    else:
        return (False, "Invalid action")


def get_valid_actions(member_details):
    """Returns a list of valid actions for this membership
    Used to condition the action buttons on the edit member view

    Args:
        member_details (MemberClubDetails): members details as returned by get_member_details

    Returns:
        list: list of strings of valid actions for this user

    Valid actions are: lapsed, resigned, terminated, deceased, change_status (at least one of
    the preceeding), paid, extend, change, reinstate, delete
    """

    if not member_details.club.full_club_admin:
        return ["delete"]

    valid_actions = []
    for action in MEMBER_ACTIONS:
        if can_perform_action(action, member_details)[0]:
            valid_actions.append(action)

    # check whether any status change is allowed
    if (
        "lapsed" in valid_actions
        or "resigned" in valid_actions
        or "terminated" in valid_actions
        or "deceased" in valid_actions
    ):
        valid_actions.append("change_status")

    return valid_actions


def get_valid_activities(member_details):
    """Returns a list of valid recent activity views for this member or contact

    This should be the only place where this business logic is represented."""

    activities = ["TAGS", "EMAILS"]

    # JPG clean-up
    # if member_details.membership_status != MemberClubDetails.MEMBERSHIP_STATUS_CONTACT:

    if member_details.user_type == f"{GLOBAL_TITLE} User":
        activities += ["ENTRIES", "SESSIONS", "TRANSACTIONS"]

    if member_details.user_type == "Unregistered User":
        activities += ["INVITATIONS"]

    return activities


# -------------------------------------------------------------------------------------
#   General data maniputation functions
# -------------------------------------------------------------------------------------


def refresh_memberships_for_club(club, as_at_date=None):
    """Ensure that the membership statuses and current memberships are correct
    for members of a club

    Args:
        club (Organisation): the club
        as_at_date (Date or None): the date to use, current if None

    Returns:
        int: number of members updated
    """

    member_details = MemberClubDetails.objects.filter(club=club)

    updated_count = 0

    for member_detail in member_details:
        if member_detail.refresh_status(as_at_date=as_at_date):
            updated_count += 1

    return updated_count


def mark_player_as_deceased(system_number, requester):
    """Mark a user or unregistered user as deceased, and cascade the
    change to any club memberships for that player. Note that this is a
    support function, not performed by the clubs.

    Args:
        system_number: the players system number

    Returns:
        boolean: success
    """

    # update the user or unregistered user record
    user = User.objects.filter(system_number=system_number).last()
    if user:
        user.deceased = True
        user.is_active = False
        user.save()
    else:
        unreg_user = UnregisteredUser.objects.filter(system_number=system_number).last()
        if unreg_user:
            unreg_user.deceased = True
            unreg_user.save()

    # update any club memberships
    member_details = MemberClubDetails.objects.filter(system_number=system_number)
    for member_detail in member_details:
        _mark_member_as_deceased(member_detail.club, member_detail, requester=requester)

    return True


def add_member(
    club,
    system_number,
    is_registered_user,
    membership_type,
    requester,
    fee=None,
    start_date=None,
    end_date=None,
    due_date=None,
    payment_method_id=-1,
    email=None,
    process_payment=True,
):
    """Add a new member and initial membership to a club.
    The person must be an existing user or unregistered user, but not a member of this club.

    Args:
        club (Organisation): the club
        system_number (int): the member's system number
        is_registered_user (bbol): is there a User onject for this person?
        membership_type (MembershipType): the membership type to be linked to
        annual_fee (Decimal): optional fee to override the default from the membership type
        start_date (Date): the start date of the membership
        end_date (Date): the end date of the membership
        due_date (Date): due date of payment
        payment_method_id (int): pk of OrgPaymentMethod or -1 if none selected
        email (str): club specific email
        process_payment (bool): attempt to make a bridge credit payment if selected payment method

    Returns:
        bool: success
        string: explanatory message or None
    """

    if not is_player_allowing_club_membership(club, system_number):
        return (False, "This user is blocking memberships from this club")

    today = timezone.now().date()

    # build the new membership record
    new_membership = MemberMembershipType(
        system_number=system_number,
        last_modified_by=requester,
        membership_type=membership_type,
        fee=fee if fee is not None else 0,
        start_date=start_date if start_date else today,
    )
    new_membership.due_date = (
        due_date
        if due_date
        else new_membership.start_date
        + timedelta(days=membership_type.grace_period_days)
    )
    if membership_type.does_not_renew:
        new_membership.end_date = None
    else:
        new_membership.end_date = end_date if end_date else club.current_end_date

    # last minute validatation

    if new_membership.start_date and new_membership.end_date:
        if new_membership.start_date > new_membership.end_date:
            return (False, "End date must be after start date")

    # proceed with payment

    payment_method = _get_payment_method(club, payment_method_id)
    payment_success, payment_message = _process_membership_payment(
        club,
        is_registered_user,
        new_membership,
        payment_method,
        "New membership",
        process_payment=process_payment,
    )

    new_membership.save()

    # create a new member details record

    member_details = MemberClubDetails(
        system_number=system_number,
        club=club,
        latest_membership=new_membership,
        membership_status=new_membership.membership_state,
        joined_date=new_membership.start_date,
    )

    if email:
        member_details.email = email

    member_details.save()

    # and log it
    message = f"Joined club ({membership_type.name})"
    if payment_message:
        message += ". " + payment_message

    log_member_change(
        club,
        system_number,
        requester,
        message,
    )

    if is_registered_user:
        user = User.objects.get(system_number=system_number)
        share_user_data_with_clubs(user, this_membership=member_details, initial=True)
        _notify_user_of_membership(member_details, user)

    return (True, message)


def _process_membership_payment(
    club,
    is_registered_user,
    membership,
    payment_method,
    description,
    process_payment=True,
):
    """
    Common processing of membership payments. On successful completion the following membership fields
    will be updated:
    - payment_method: None if none specified or nothing to pay
    - is_paid: False if Bridge Credits payment failed or not processed, True even if fee is zero
    - paid_until_date: will be None if not paid, or set to the start_date if paid (or zero fee)
    - membership_state: based on payment status, effectiove dates and due date

    Args:
        club (Organisation): the club
        is_registered_user (bool): is there a User object for this person
        membership (MemberMembershipTYpe): Must have the system_number, fee, membership_type and end_date set
        payment_method (OrgPaymentMethod): payment method to be used, or None
        description (str): description to be used on the payment transactions
        process_payments (bool): should a Bridge Credit payment be processed (if the select method)?

    Returns:
        bool: False if unable to process the Bridge Credits, the payment method is invalid or already paid
        str: a status message

    Note:
    - Does not save the membership, this must be done by the caller
    - Returns immediately if is_paid already set.
    - Logs errors if issues with Bridge Credits payments
    """

    from payments.views.payments_api import payment_api_batch

    message = ""
    success = True

    if membership.is_paid:
        return (False, "Already paid")

    def _has_paid(ok):
        """Updates when paid status is known"""

        membership.is_paid = ok
        membership.paid_until_date = membership.end_date if ok else None

        today = timezone.now().date()
        if ok:
            membership.paid_date = today
            membership.auto_pay_date = None
            if membership.is_in_effect:
                membership.membership_state = (
                    MemberMembershipType.MEMBERSHIP_STATE_CURRENT
                )
            elif membership.start_date > today:
                membership.membership_state = (
                    MemberMembershipType.MEMBERSHIP_STATE_FUTURE
                )
            else:
                # should never happen (creating a membership in the past) ...
                membership.membership_state = (
                    MemberMembershipType.MEMBERSHIP_STATE_LAPSED
                )
        else:
            if membership.fee == 0:
                membership.membership_state = (
                    MemberMembershipType.MEMBERSHIP_STATE_CURRENT
                )
            elif membership.start_date > today:
                membership.membership_state = (
                    MemberMembershipType.MEMBERSHIP_STATE_FUTURE
                )
            elif membership.due_date >= today:
                membership.membership_state = MemberMembershipType.MEMBERSHIP_STATE_DUE
            else:
                # something has gone wrong, past due but not paid successfully
                # make due date today to give a chance of recovery
                # JPG - perhaps should have an "overdue" status as well as lapsed?
                membership.due_date = today
                membership.membership_state = MemberMembershipType.MEMBERSHIP_STATE_DUE

    if membership.fee == 0:
        # nothing to pay so ignore everything else
        membership.payment_method = None
        _has_paid(True)
        return (True, "Nothing to pay")

    # check the payment method
    if payment_method:
        if payment_method.payment_method == "Bridge Credits" and not is_registered_user:
            membership.payment_method = None
            _has_paid(False)
            logger.error(
                f"Unregistered {membership.system_number} cannot pay with {BRIDGE_CREDITS}"
            )
            return (False, f"Only registered users can use {BRIDGE_CREDITS}")

    membership.payment_method = payment_method

    if payment_method:
        if payment_method.payment_method == "Bridge Credits":

            if process_payment:
                # try to make the payment

                user = User.objects.get(system_number=membership.system_number)

                if payment_api_batch(
                    member=user,
                    description=description,
                    amount=membership.fee,
                    organisation=club,
                    payment_type="Club Membership",
                    book_internals=True,
                ):
                    # Payment successful
                    _has_paid(True)
                    message = f"Paid by {BRIDGE_CREDITS}"
                else:
                    # Payment failed, leave as unpaid
                    logger.error("Error processing Bridge Credits payment")
                    _has_paid(False)
                    success = False
                    message = f"{BRIDGE_CREDITS} payment UNSUCCESSFUL"
            else:
                _has_paid(False)
                message = f"{BRIDGE_CREDITS} payment not attempted"
        else:
            # off system payment, always mark as paid
            _has_paid(True)
            message = f"Paid by {payment_method.payment_method}"
    else:
        _has_paid(False)
        message = "No payment method specified"

    return (success, message)


# -------------------------------------------------------------------------------------
#   Action functions
#
#   Functions to implement the actions listed in MEMBER_ACTIONS. Actions can be
#   considered either simple or complex, where complex actions require arguements
#   beyond the action name, club and member_details.
#
#   Simple actions are implemented by private functions with a standard signature:
#
#   Args:
#       club (Organisation): the member's club
#       member_details (MemberClubDetails): the members details
#       requester (User): actioning user for logging purposes
#   Returns:
#       bool: success
#       str: explanatory message or None
#
#   Access to these functions is through perform_simple_action(...)
#
#   To add a simple action:
#       - do the updates required for a validation function (see above)
#       - create the private action function
#       - add the function to SIMPLE_ACTION_FUNCTIONS
#
#   Simple action functions can assume that the member details have already been
#   validated for that action before being called. Where possible
#   _update_member_function should be call to do simple actual status updates.
#
#   Complex actions are handled by individual public functions to cater for the
#   additional parameters required. Such functions should call the associated validation
#   function to validate teh members state before executing the post logic
# -------------------------------------------------------------------------------------

# -------------------------------------------------------------------------------------
#   Simple action functions
# -------------------------------------------------------------------------------------


def _mark_member_as_deceased(club, member_details, requester=None):
    """Mark a club member as deceased. Note that this only applies
    at the club level. Marking a user or unregistered user as deceased
    is a support function, achieved through mark_player_as_deceased.
    If the member is a contact, it will be deleted.

    Args:
        club (Organisation): the club
        system_number: member's system number
        requester (User): the user requesting the change

    Returns:
        bool: success
        str: message

    Raises:
        CobaltMemberNotFound: if no member found with this system number
    """

    # just delete deceased contacts
    if member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_CONTACT:
        member_details.delete()
        return (True, "Contact deleted")

    #  if there is a current membership type association, mark it as deceased and end it
    if (
        member_details.latest_membership
        and member_details.latest_membership.membership_state
        in [
            MemberMembershipType.MEMBERSHIP_STATE_CURRENT,
            MemberMembershipType.MEMBERSHIP_STATE_DUE,
        ]
    ):
        member_details.latest_membership.membership_state = (
            MemberMembershipType.MEMBERSHIP_STATE_DECEASED
        )
        member_details.latest_membership.save()

    member_details.previous_membership_status = member_details.membership_status
    member_details.membership_status = MemberClubDetails.MEMBERSHIP_STATUS_DECEASED
    member_details.save()

    old_status_desc = member_details.get_previous_membership_status_display()
    message = f"Status changed from {old_status_desc} to Deceased"

    log_member_change(
        club,
        member_details.system_number,
        requester,
        message,
    )

    return (True, message)


def _mark_member_as_lapsed(club, member_details, requester=None):
    """Mark the member's current membership as lapsed"""

    return _update_member_status(
        club,
        member_details,
        MemberMembershipType.MEMBERSHIP_STATE_LAPSED,
        "lapsed",
        requester=requester,
    )


def _mark_member_as_resigned(club, member_details, requester=None):
    """Mark the member as resigned"""

    return _update_member_status(
        club,
        member_details,
        MemberMembershipType.MEMBERSHIP_STATE_RESIGNED,
        "resigned",
        requester=requester,
    )


def _mark_member_as_terminated(club, member_details, requester=None):
    """Mark the member's current membership as terminated"""

    return _update_member_status(
        club,
        member_details,
        MemberMembershipType.MEMBERSHIP_STATE_TERMINATED,
        "terminated",
        requester=requester,
    )


def _check_left_date(member_details):
    """Ensure that the left date is appropriate after a status change"""
    if member_details.membership_status in MEMBERSHIP_STATES_TERMINAL:
        if not member_details.left_date:
            member_details.left_date = timezone.now().date()
    else:
        member_details.left_date = None


def _reinstate_previous_status(club, member_details, requester=None):
    """Reinstate a users last membership status if possible"""

    # swap previous and current statuses
    replaced_status = member_details.membership_status
    member_details.membership_status = member_details.previous_membership_status
    member_details.previous_membership_status = replaced_status

    # check whether was previousl a contact
    if member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_CONTACT:
        member_details.latest_membership.delete()
        member_details.latest_membership = None
        member_details.save()
        return (True, "Member reverted to being a contact")

    # check date sensitive statuses are still valid
    today = timezone.now().date()
    if member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_CURRENT:
        if (
            member_details.latest_membership.end_date
            and member_details.latest_membership.end_date < today
        ):
            member_details.membership_status = (
                MemberClubDetails.MEMBERSHIP_STATUS_LAPSED
            )
    elif member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_DUE:
        if member_details.latest_membership.due_date < today:
            member_details.membership_status = (
                MemberClubDetails.MEMBERSHIP_STATUS_LAPSED
            )

    _check_left_date(member_details)

    member_details.save()

    # update the membership record
    member_details.latest_membership.membership_state = member_details.membership_status
    member_details.latest_membership.save()

    message = f"Reinstated {member_details.get_membership_status_display()} status from {member_details.get_previous_membership_status_display()}"

    log_member_change(
        club,
        member_details.system_number,
        requester,
        message,
    )

    return (True, message)


def _update_member_status(club, member_details, new_status, action, requester=None):
    """Private function to handle membership status changes.
    The membership status and the state and end date of the latest membership type are updated.
    Validates state using can_perform_actiuon.

    A log record is written if successful

    Args:
        club (Organisaton): the club
        member_details (MemberClubDetails): the member's system number
        new_status (MemberClubDetail.MEMBERSHIP_STATUS): the status to be assigned
        action (str): the action name, to check validity of current state
        requester (User): the user requesting the change

    Returns:
        bool: success or failure
        string: explanatory message

    Raises:
        CobaltMemberNotFound: if no member found with this system number
    """

    yesterday = timezone.now().date() - timedelta(days=1)
    if new_status not in MEMBERSHIP_STATES_TERMINAL:
        member_details.latest_membership.end_date = yesterday
    member_details.latest_membership.membership_state = new_status

    member_details.previous_membership_status = member_details.membership_status
    member_details.membership_status = new_status

    _check_left_date(member_details)

    member_details.save()
    member_details.latest_membership.save()

    message = f"Status changed from {member_details.get_previous_membership_status_display()} to {member_details.get_membership_status_display()}"

    log_member_change(
        club,
        member_details.system_number,
        requester,
        message,
    )

    return (True, message)


def _mark_member_as_paid(club, member_details, requester=None):
    """Mark a member as paid. Sets the paid until to be the end date, sets the paid date, changes the status and removes the due date and auto-pay date. Logs the update."""

    today = timezone.now().date()

    member_details.latest_membership.state = (
        MemberMembershipType.MEMBERSHIP_STATE_CURRENT
    )
    member_details.latest_membership.due_date = None
    member_details.paid_date = today
    member_details.auto_pay_date = None
    member_details.latest_membership.paid_until_date = (
        member_details.latest_membership.end_date
    )
    member_details.latest_membership.save()

    member_details.membership_status = MemberClubDetails.MEMBERSHIP_STATUS_CURRENT
    member_details.save()

    message = f"Member marked as paid ({member_details.latest_membership.fee} fee)"

    log_member_change(
        club,
        member_details.system_number,
        requester,
        message,
    )

    return (True, message)


def _delete_member(club, member_details, requester=None):
    """Delete a member - the member will become a contact"""

    # delete all associated membership records
    member_details.latest_membership = None

    MemberMembershipType.objects.filter(
        system_number=member_details.system_number, membership_type__organisation=club
    ).delete()

    # remove other membership data from the member details
    member_details.previous_membership_status = member_details.membership_status
    member_details.membership_status = MemberClubDetails.MEMBERSHIP_STATUS_CONTACT
    member_details.joined_date = None
    member_details.left_date = None
    member_details.save()

    log_member_change(
        club,
        member_details.system_number,
        requester,
        "Membership deleted. Details saved as a contact",
    )

    return (True, "Membership information deleted. Details saved as a contact")


SIMPLE_ACTION_FUNCTIONS = {
    "lapsed": _mark_member_as_lapsed,
    "resigned": _mark_member_as_resigned,
    "terminated": _mark_member_as_terminated,
    "deceased": _mark_member_as_deceased,
    "paid": _mark_member_as_paid,
    "reinstate": _reinstate_previous_status,
    "delete": _delete_member,
}


def perform_simple_action(action_name, club, system_number, requester=None):
    """Public access to perform simple actions on members

    Args:
        action_name (str): an action name in SIMPLE_ACTION_FUNCTIONS
        club (Oragisation): the member's club
        system_number (int): the member's system number
        requestor (User): the actioning user for logging purposes

    Returns:
        bool: success
        str: explanatory message
    """

    if action_name not in SIMPLE_ACTION_FUNCTIONS:
        return (False, f"Invalid action '{action_name}'")

    member_details = (
        MemberClubDetails.objects.filter(
            club=club,
            system_number=system_number,
        )
        .select_related("latest_membership")
        .last()
    )

    if not member_details:
        raise CobaltMemberNotFound(club, system_number)

    permitted_action, message = can_perform_action(action_name, member_details)

    if not permitted_action:
        return (False, message)

    return SIMPLE_ACTION_FUNCTIONS[action_name](
        club, member_details, requester=requester
    )


# -------------------------------------------------------------------------------------
#   Complex action functions (those requiring additional arguements)
# -------------------------------------------------------------------------------------


def _get_payment_method(club, payment_method_id):
    """Returns a club payment method or None, based on the id choice from
    a drop down list (-1 if not selected)

    Args:
        club (Organisation): the club
        payment_method_id (int): the payment method id or -1 if not specified

    Returns:
        OrgPaymentMethod: or none if invalid or not selected
    """

    if payment_method_id >= 0:
        try:
            payment_method = OrgPaymentMethod.objects.get(pk=payment_method_id)
            if payment_method.organisation != club or payment_method.active is False:
                payment_method = None
        except OrgPaymentMethod.DoesNotExist:
            payment_method = None
    else:
        payment_method = None

    return payment_method


def make_membership_payment(
    club,
    membership,
    payment_method_id,
    requester=None,
):
    """Make (or record) a payment for a membership

    Args:
        club (Organisation): the club
        membership (MemberMembershipType): the membership to pay
        payment_method_id (int): pk of OrgPaymentMethod

    Returns:
        bool: success
        str: message
    """

    if membership.membership_state not in [
        MemberMembershipType.MEMBERSHIP_STATE_CURRENT,
        MemberMembershipType.MEMBERSHIP_STATE_FUTURE,
        MemberMembershipType.MEMBERSHIP_STATE_DUE,
    ]:
        return (False, "Can only make payments for current, due or future memberships")

    user_check = User.objects.filter(system_number=membership.system_number).last()

    payment_method = _get_payment_method(club, payment_method_id)

    payment_success, payment_message = _process_membership_payment(
        club,
        (user_check is not None),
        membership,
        payment_method,
        f"Membership fee ({membership.membership_type.name})",
    )

    membership.save()

    if payment_success:
        # see if the member details level needs to be updated
        member_details = MemberClubDetails.objects.get(
            system_number=membership.system_number,
            club=club,
        )
        if member_details.latest_membership == membership:
            # generally should just make it current, but there might be edge
            # cases with paying historic memberships. Leave that to user to edit
            member_details.membership_status = (
                MemberClubDetails.MEMBERSHIP_STATUS_CURRENT
            )
            member_details.save()

    log_member_change(
        club,
        membership.system_number,
        requester,
        payment_message,
    )

    return (payment_success, payment_message)


def renew_membership(
    member_details,
    renewal_parameters,
    batch_id=None,
    process_payment=False,
    requester=None,
):
    """Extend the members current membership type for a new period.
    Uses the current membership type and start date is continued from current
    emd date.

    Args:
        membership_details (MemberClubDetails): augmented by get_members_for_renewal
        renewal_parameters (RenewalParameters): the parameters
        batch_id (BatchID): the rbac batch id for this batch of renewals, or None if a single
        requester (User): the requesting user

    Returns:
        bool: success
        string: explanatory message or None
    """

    message = ""

    permitted_action, message = can_perform_action("extend", member_details)
    if not permitted_action:
        return (False, message)

    if renewal_parameters.end_date <= member_details.latest_membership.end_date:
        return (False, "New end date must be later than the current end date")

    # create a new membership record

    new_membership = MemberMembershipType(
        system_number=member_details.system_number,
        membership_type=renewal_parameters.membership_type,
        start_date=renewal_parameters.start_date,
        due_date=renewal_parameters.due_date,
        end_date=renewal_parameters.end_date,
        auto_pay_date=renewal_parameters.auto_pay_date,
        fee=renewal_parameters.fee,
        last_modified_by=requester,
        membership_state=MemberMembershipType.MEMBERSHIP_STATE_FUTURE,
    )

    # note: membership state will be updated by the payment process

    payment_success, payment_message = _process_membership_payment(
        renewal_parameters.club,
        (member_details.user_type == f"{GLOBAL_TITLE} User"),
        new_membership,
        renewal_parameters.payment_method,
        "Membership renewal",
        process_payment=process_payment,
    )

    if payment_message:
        message = payment_message

    new_membership.save()

    # NOTE: assuming that renewals always occur while the current membership is active
    # nothin needs to be done to the current membership details or membership

    log_member_change(
        renewal_parameters.club,
        member_details.system_number,
        requester,
        f"{member_details.latest_membership.membership_type.name} membership extended from "
        + f"{new_membership.start_date.strftime('%d-%m-%Y')} to {new_membership.end_date.strftime('%d-%m-%Y')}",
    )

    if renewal_parameters.send_notice:

        send_renewal_notice(
            member_details,
            renewal_parameters,
            batch_id=batch_id,
        )

    if new_membership.is_paid:
        if new_membership.fee and new_membership.payment_method:
            log_member_change(
                renewal_parameters.club,
                member_details.system_number,
                requester,
                f"Membership paid using {new_membership.payment_method.payment_method}",
            )

    return (True, "Membership extended" + (f". {message}" if message else ""))


def _format_renewal_notice_email(
    member_details, renewal_parameters, test_email_address=None
):
    """Returns the email address and context for a renewal notice

    Args:
        member_details (MemberContactDetails): the member details (augmented as per get_members_for_renewal)
        renewal_parameters (RenewalParameters): the renewal parameters
        test_email_address (str): an email address to override the member email for a test message

    Returns:
        str: email address or None
        dict: email rendering context
    """

    if test_email_address:
        club_email = test_email_address
    else:
        club_email = member_details.club_email
        # club_email = club_email_for_member(member_details.club, member_details.system_number)

    if not club_email:
        return (None, {})

    # generate a summary of the renewal details and payment options to append to the user provided content
    # NOTE: normally the global settings are added to the context by gloabl_settings context processor
    # but this does not happen here
    auto_content = render_to_string(
        "organisations/club_menu/members/renewal_notice_content.html",
        {
            "member_details": member_details,
            "renewal_parameters": renewal_parameters,
            "GLOBAL_TITLE": GLOBAL_TITLE,
            "BRIDGE_CREDITS": BRIDGE_CREDITS,
        },
    )

    context = {
        "title": renewal_parameters.email_subject,
        "subject": renewal_parameters.email_subject,
        "name": member_details.first_name,
        "email_body": renewal_parameters.email_content + auto_content,
    }

    if renewal_parameters.club_template:
        #  apply club template styling

        if renewal_parameters.club_template.banner:
            context["img_src"] = renewal_parameters.club_template.banner.url
        if renewal_parameters.club_template.footer:
            context["footer"] = renewal_parameters.club_template.footer
        if renewal_parameters.club_template.box_colour:
            context["box_colour"] = renewal_parameters.club_template.box_colour
        if renewal_parameters.club_template.box_font_colour:
            context[
                "box_font_colour"
            ] = renewal_parameters.club_template.box_font_colour
        if renewal_parameters.club_template.reply_to:
            context["reply_to"] = renewal_parameters.club_template.reply_to
        if renewal_parameters.club_template.from_name:
            context["from_name"] = renewal_parameters.club_template.from_name

    return (club_email, context)


def send_renewal_notice(
    member_details, renewal_parameters, batch_id=None, test_email_address=None
):
    """Send an email renewal notice.
    Includes a system generated portion explaining Bridge Credit payment options
    if appropriate (ie registered user and not paid).

    Args:
        member_details (MemberClubDetails): augmented member details
        renewal_parameters (RenewalParameters): the parameters
        batch_id (RBACBathcId): if sending as part of a batch
        test_email_address (string): override members email to send a test message

    Returns:
        bool: success
        str: explanatory message if failed, or None
    """

    from notifications.views.core import send_cobalt_email_with_template

    # generate some meaningful content to append to the user provided content
    club_email, context = _format_renewal_notice_email(
        member_details,
        renewal_parameters,
        test_email_address=test_email_address,
    )

    if not club_email:
        return (False, "No email address available")

    if test_email_address:
        # Do not associate test emails with a batch
        this_batch_id = None
    else:
        if batch_id:
            this_batch_id = batch_id
        else:
            # Create batch id so admins can see this email

            from notifications.views.core import create_rbac_batch_id

            this_batch_id = create_rbac_batch_id(
                rbac_role=f"notifications.orgcomms.{renewal_parameters.club.id}.edit",
                organisation=renewal_parameters.club,
                batch_type=BatchID.BATCH_TYPE_COMMS,
                batch_size=1,
                description=renewal_parameters.email_subject,
                complete=True,
            )

    send_cobalt_email_with_template(
        to_address=club_email,
        context=context,
        batch_id=this_batch_id,
        batch_size=this_batch_id.batch_size if this_batch_id else 1,
        apply_default_template_for_club=member_details.club
        if renewal_parameters.club_template is None
        else None,
    )

    return (True, None)


def change_membership(
    club,
    system_number,
    membership_type,
    requester,
    fee=None,
    start_date=None,
    end_date=None,
    due_date=None,
    payment_method_id=-1,
    process_payment=False,
):
    """Change the membership type for an existing club member by adding a new MemberMembershipType.
    The member may have a current membership, or may have lapsed, resigned etc.
    The member must not be deceased or a contact

    Args:
        club (Organisation): the club
        system_number (int): the member's system number
        membership_type (MembershipType): the new membership type to be linked to
        requester (User): the user making teh change, required for the new record
        fee (Decimal): optional fee to override the default from the membership type
        start_date (Date): optional start date, otherwise will use today
        end_date (Date): optional end date, otherwise will use the club default or None if perpetual
        due_date (Date): optional due_date, otherwise use the payment type grace period if a fees is set
        is_paid (bool): has the fee been paid, used to set the paid until date

    Returns:
        bool: success
        string: explanatory message or None

    Raises:
        CobaltMemberNotFound : no member record found
    """

    today = timezone.now().date()

    member_details = get_member_details(club, system_number)

    if not member_details:
        raise CobaltMemberNotFound(club, system_number)

    permitted_action, message = can_perform_action("change", member_details)

    if not permitted_action:
        return (False, message)

    # allow any start date. Work out when to end the current

    start_date_for_new = start_date if start_date else today
    if member_details.latest_membership.end_date:
        is_after_current = (
            start_date_for_new > member_details.latest_membership.end_date
        )
    else:
        #  current has no end date (ie perptual), so will need to end it
        is_after_current = False

    if is_after_current:
        # no change
        end_date_for_current = member_details.latest_membership.end_date

        if member_details.membership_status in MEMBERSHIP_STATES_TERMINAL:
            # not an active member, so new membership should start today
            if start_date_for_new != today:
                return False, "New membership cannot start in the future"
        elif end_date_for_current != start_date_for_new - timedelta(days=1):
            return (
                False,
                "New membership must start at or before the end of the current",
            )
    else:
        end_date_for_current = start_date_for_new - timedelta(days=1)
        if end_date_for_current < member_details.latest_membership.start_date:
            # would be odd to back-date before the start of the current, but handle it sensibly anyway
            return (
                False,
                "New membership cannot be back dated before the start of the current",
            )

    # build the new membership record
    new_membership = MemberMembershipType(
        system_number=system_number,
        last_modified_by=requester,
        membership_type=membership_type,
        fee=fee if fee is not None else 0,
        start_date=start_date_for_new,
    )

    if membership_type.does_not_renew:
        new_membership.end_date = None
    else:
        new_membership.end_date = end_date if end_date else club.current_end_date

    new_membership.due_date = (
        due_date
        if due_date
        else new_membership.start_date
        + timedelta(days=membership_type.grace_period_days)
    )

    # last minute validatation
    if new_membership.start_date and new_membership.end_date:
        if new_membership.start_date > new_membership.end_date:
            return (False, "End date must be after start date")

    # try to process payment

    payment_method = _get_payment_method(club, payment_method_id)

    payment_success, payment_message = _process_membership_payment(
        club,
        (member_details.user_type == f"{GLOBAL_TITLE} User"),
        new_membership,
        payment_method,
        "Membership",
        process_payment=process_payment,
    )

    new_membership.save()

    # update the member record and the previous membership record

    if (
        member_details.latest_membership.membership_state in MEMBERSHIP_STATES_ACTIVE
        and end_date_for_current != member_details.latest_membership.end_date
    ):
        member_details.latest_membership.end_date = end_date_for_current
        if end_date_for_current < today:
            # old membership is now over
            member_details.latest_membership.membership_state = (
                MemberMembershipType.MEMBERSHIP_STATE_ENDED
            )
        member_details.latest_membership.save()

    if end_date_for_current < today:
        if new_membership.start_date <= today:
            # new membership takes effect
            member_details.latest_membership = new_membership
            member_details.membership_status = new_membership.membership_state
        else:
            # old one has ended, new one has not start (odd condition but anyway)
            member_details.membership_status = MemberClubDetails.MEMBERSHIP_STATUS_ENDED
        member_details.save()

    # and log it
    message = f"Membership changed to {membership_type.name}"
    if payment_message:
        message += ". " + payment_message

    log_member_change(
        club,
        system_number,
        requester,
        message,
    )

    return (True, message)


def share_user_data_with_clubs(user, this_membership=None, initial=False):
    """Share user personal information with clubs of which they are a member

    Args:
        user (User): the user electing to share information
        this_membership (MemberClubDetails): only update this membership
        initail (bool): is this the first time sharing this data?

    Returns:
        int: number of clubs updated
    """

    additional_info = user.useradditionalinfo_set.last()

    if this_membership:
        memberships = [this_membership]
    else:
        memberships = get_club_memberships_for_person(user.system_number)

    updated_clubs = 0
    for membership in memberships:
        updated = False

        # check sharing options
        club_options = MemberClubOptions.objects.filter(
            club=membership.club,
            user=user,
        ).last()

        if (
            not club_options
            or club_options.share_data == MemberClubOptions.SHARE_DATA_NEVER
            or (
                club_options.share_data == MemberClubOptions.SHARE_DATA_ONCE
                and not initial
            )
        ):
            continue

        overwrite = club_options.share_data == MemberClubOptions.SHARE_DATA_ALWAYS

        # update any fields
        for profile_field_name, club_field_name in [
            ("email", "email"),
            ("dob", "dob"),
            ("mobile", "preferred_phone"),
        ]:
            if getattr(user, profile_field_name) and (
                not getattr(membership, club_field_name) or overwrite
            ):
                setattr(membership, club_field_name, getattr(user, profile_field_name))
                updated = True

        # if the club is using the same email make sure that the email bounce data
        # is synchronised

        if (
            additional_info
            and membership.email == user.email
            and membership.email_hard_bounce != additional_info.email_hard_bounce
        ):
            membership.email_hard_bounce = additional_info.email_hard_bounce
            membership.email_hard_bounce_reason = (
                additional_info.email_hard_bounce_reason
            )
            membership.email_hard_bounce_date = additional_info.email_hard_bounce_date

        if updated:
            membership.save()
            log_member_change(
                membership.club,
                user.system_number,
                user,
                "Updated with data shared by member",
            )
            updated_clubs += 1

    return updated_clubs


# -------------------------------------------------------------------------------------
# Data conversion functions
# -------------------------------------------------------------------------------------


def convert_existing_membership(club, membership):
    """Conversion logic to populate a MemberMembershipType record and
    create a corresponding MemberClubDetails record. NOTE: this is only for
    data conversion use following the migration to the Release 6 data model.

    Args:
        club (Organisation): the owning club
        membership (MemberMembershipType): an existing old membership record

    Raises:
        UnregisteredUser.DoesNotExist: if no User or UnregisteredUser found
    """

    # get the user or unregistered user record for this member
    user = User.objects.filter(system_number=membership.system_number).last()
    if user:
        is_user = True
        deceased = user.deceased
    else:
        unreg_user = UnregisteredUser.objects.get(
            system_number=membership.system_number
        )
        # will raise an exception if not found
        is_user = False
        deceased = unreg_user.deceased

    if deceased:
        today = timezone.now().date()
        membership.end_date = today
        membership.paid_until_date = today
        membership.membership_state = MemberMembershipType.MEMBERSHIP_STATE_DECEASED
    else:
        # assume that the membership is current and paid until the end of the current membership year
        membership.is_paid = True
        if membership.membership_type.does_not_renew:
            membership.end_date = None
        else:
            membership.end_date = club.current_end_date
        membership.paid_until_date = membership.end_date
        membership.membership_state = MemberMembershipType.MEMBERSHIP_STATE_CURRENT

    membership.save()

    # check for an existing member detail record, in case executed twice
    member_details = MemberClubDetails.objects.filter(
        club=club,
        system_number=membership.system_number,
    ).last()

    if not member_details:
        # create a club member details record
        member_details = MemberClubDetails()

    member_details.system_number = membership.system_number
    member_details.club = club
    member_details.latest_membership = membership
    member_details.joined_date = None

    if deceased:
        member_details.membership_status = MemberClubDetails.MEMBERSHIP_STATUS_DECEASED
    else:
        member_details.membership_status = MemberClubDetails.MEMBERSHIP_STATUS_CURRENT

        club_email = MemberClubEmail.objects.filter(
            organisation=club,
            system_number=membership.system_number,
        ).last()

        if club_email:
            member_details.email = club_email.email
            member_details.email_hard_bounce = club_email.email_hard_bounce
            member_details.email_hard_bounce_reason = (
                club_email.email_hard_bounce_reason
            )
            member_details.email_hard_bounce_date = club_email.email_hard_bounce_date

    member_details.save()

    if is_user:
        share_user_data_with_clubs(user, this_membership=member_details, initial=True)


def convert_existing_memberships_for_club(club):
    """Conversion logic to populate a MemberMembershipType record and
    create corresponding MemberClubDetails records for a club. Logs errors
    if unable to convert a record.
    NOTE: this is only for data conversion use following the migration to the
    Release 6 data model.

    Args:
        club (Organisation): the club to be converted

    Returns:
        int: number of memberships converted successfully
        int: number of memberships not converted (errored)
    """

    # get the existing membership records for the club
    memberships = MemberMembershipType.objects.filter(
        membership_type__organisation=club
    )

    ok_count = 0
    error_count = 0
    for membership in memberships:
        try:
            convert_existing_membership(club, membership)
            ok_count += 1
        except UnregisteredUser.DoesNotExist:
            error_count += 1
            logger.error(
                f"Unable to convert MemberMembershipType {membership} for {club}, no matching user"
            )

    return (ok_count, error_count)


# -------------------------------------------------------------------------------------
# Contacts functions
# -------------------------------------------------------------------------------------


def add_contact_with_system_number(club, system_number):
    """Add a contact with the specified details"""

    contact_details = MemberClubDetails()
    contact_details.club = club
    contact_details.system_number = system_number
    contact_details.membership_status = MemberClubDetails.MEMBERSHIP_STATUS_CONTACT
    contact_details.save()


def _replace_internal_system_number(internal_number, real_number):
    """Replace all occurances of an internal system number with a real number"""

    Recipient.objects.filter(system_number=internal_number).update(
        system_number=real_number
    )

    MemberClubTag.objects.filter(system_number=internal_number).update(
        system_number=real_number
    )

    ClubMemberLog.objects.filter(system_number=internal_number).update(
        system_number=real_number
    )


def convert_contact_to_member(
    club,
    old_system_number,
    system_number,
    membership_type,
    requester,
    fee=None,
    start_date=None,
    end_date=None,
    due_date=None,
    payment_method_id=-1,
    process_payment=True,
):
    """Convert a club contact to a member with the supplied parameters.

    The contact may be a User, UnregisteredUser with an ABF number or an UnregisteredUser with
    an internal system number.

    Args:
        club (Organisation): the club
        old_system_number (int): the contact's current system number (could be internal)
        system_number (int): the system number to be used as the member (must not be internal)
        membership_type (MembershipType): the membership type to be linked to
        requester (User): the user making teh change, required for the new record
        fee (Decimal): optional fee to override the default from the membership type
        start_date (Date): optional start date, otherwise will use today
        end_date (Date): optional end date, otherwise will use the club default or None if perpetual
        due_date (Date): optional due_date, otherwise use the payment type grace period
        payment_method_id (int): pk for OrgPaymentMethod or -1 if none specified
        process_payment (bool): attempt to process Bridge Credit payment

    Returns:
        bool: success
        string: explanatory message or None
    """

    if not is_player_allowing_club_membership(club, system_number):
        return (False, "This user is blocking memberships from this club")

    today = timezone.now().date()

    start_date_actual = start_date if start_date else today
    if membership_type.does_not_renew:
        end_date_actual = None
    else:
        end_date_actual = end_date if end_date else club.current_end_date

    # do validatation before hitting the database

    if start_date_actual > today:
        return (False, "Start date cannot be in the future")

    if end_date_actual:
        if start_date_actual > end_date_actual:
            return (False, "End date must be after start date")

    # ok to proceeed

    member_details = MemberClubDetails.objects.get(
        club=club,
        system_number=old_system_number,
    )

    def _get_user_or_unreg(a_system_number):
        """look for a user or unregistered user from a system number"""
        u_or_u = User.objects.filter(
            system_number=a_system_number,
        ).last()
        if not u_or_u:
            u_or_u = UnregisteredUser.all_objects.filter(
                system_number=a_system_number
            ).last()
        return u_or_u

    # can only be changing system numbers because current is internal
    is_real_system_number = system_number == old_system_number

    # there will always be an existing unreg at least for the old_system number
    existing_user_or_unreg = _get_user_or_unreg(old_system_number)
    if is_real_system_number:
        new_user_or_unreg = existing_user_or_unreg
    else:
        # check for an existing user or unreg with the new number
        new_user_or_unreg = _get_user_or_unreg(system_number)

    if not is_real_system_number:
        # deal with a contact with an internal system number

        if new_user_or_unreg:
            # actual user is on the system so can delete the old internal unreg
            existing_user_or_unreg.delete()
        else:
            # actual user not on the system so convert the existing unreg user
            # AND ensure that their name is consisten with the MPC

            # Get data from the MPC
            mpc_details = user_summary(system_number)
            existing_user_or_unreg.last_name = mpc_details["Surname"]
            existing_user_or_unreg.first_name = mpc_details["GivenNames"]

            existing_user_or_unreg.system_number = system_number
            existing_user_or_unreg.internal_system_number = False
            existing_user_or_unreg.save()
            new_user_or_unreg = existing_user_or_unreg

        member_details.system_number = system_number
        _replace_internal_system_number(old_system_number, system_number)

    # now have a User or UnregisteredUser for the new number

    # build the new membership record
    new_membership = MemberMembershipType(
        system_number=system_number,
        last_modified_by=requester,
        membership_type=membership_type,
        fee=fee if fee is not None else 0,
        start_date=start_date_actual,
        end_date=end_date_actual,
    )
    new_membership.due_date = (
        due_date
        if due_date
        else new_membership.start_date
        + timedelta(days=membership_type.grace_period_days)
    )

    payment_method = _get_payment_method(club, payment_method_id)

    payment_success, payment_message = _process_membership_payment(
        club,
        (type(new_user_or_unreg) == User),
        new_membership,
        payment_method,
        "New membership",
        process_payment=process_payment,
    )

    new_membership.save()

    # update the member detail record (the old contact object)

    member_details.latest_membership = new_membership
    member_details.membership_status = new_membership.membership_state
    member_details.joined_date = new_membership.start_date

    member_details.save()

    # and log it
    message = f"Contact converted to member ({membership_type.name})"
    if payment_message:
        message += ". " + payment_message

    log_member_change(
        club,
        system_number,
        requester,
        message,
    )

    if type(new_user_or_unreg) == User:
        share_user_data_with_clubs(
            new_user_or_unreg,
            this_membership=member_details,
            initial=True,
        )
        _notify_user_of_membership(member_details, new_user_or_unreg)

    return (True, message)


def delete_contact(club, system_number):
    """Delete a contact"""

    contact_details = MemberClubDetails.objects.get(
        club=club, system_number=system_number
    )

    if contact_details.membership_status != MemberClubDetails.MEMBERSHIP_STATUS_CONTACT:
        return (False, "This person is notr a contact of the club")

    contact_unreg_user = UnregisteredUser.all_objects.filter(
        system_number=system_number
    ).last()

    if contact_unreg_user and contact_unreg_user.internal_system_number:
        # delete the unregistered user record and any recipient entries

        contact_unreg_user.delete()

        Recipient.objects.filter(system_number=system_number).delete()

    # delete membership related entries for this club

    MemberClubTag.objects.filter(
        club_tag__organisation=club, system_number=system_number
    ).delete()

    MemberClubDetails.objects.filter(club=club, system_number=system_number).delete()

    ClubMemberLog.objects.filter(club=club, system_number=system_number)

    return (True, "Contact deleted")


def block_club_for_user(club_id, user):
    """Take all actions to block membership of a club for a registered user

    The user's club option record is updated, any current membership is deleted
    and the club is sent an email notification.

    Args:
        club_id (int): the id of the club to block
        user (User): the user requesting the block

    Returns:
        bool: success
        str: error message if failed, or None
        Organisation: the club, or None if there was a problem
    """

    try:
        club = Organisation.objects.get(pk=club_id)
    except Organisation.DoesNotExist:
        return (False, "No such club", None)

    #  update or create the options record

    club_options = MemberClubOptions.objects.filter(
        club=club,
        user=user,
    ).last()

    if club_options:
        club_options.allow_membership = False
    else:
        club_options = MemberClubOptions(
            user=user,
            club=club,
            allow_membership=False,
        )
    club_options.save()

    # delete the membership

    member_details = MemberClubDetails.objects.filter(
        system_number=user.system_number,
        club=club,
    ).last()

    if member_details:
        _delete_member(club, member_details, user)

    # email the club

    _notify_club_of_block(club, user)

    # log it

    log_member_change(
        club,
        user.system_number,
        user,
        "User has blocked club membership",
    )

    ClubLog(
        organisation=club,
        actor=user,
        action=f"{user} has blocked club membership",
    ).save()

    return (True, None, None)


def unblock_club_for_user(club_id, user):
    """Take all actions to unblock membership of a club for a registered user

    The user's club option record is deleted.

    Args:
        club_id (int): the id of the club to block
        user (User): the user requesting the block

    Returns:
        bool: success
        str: error message if failed, or None
        Organisation: the club, or None if there was a problem
    """

    try:
        club = Organisation.objects.get(pk=club_id)
    except Organisation.DoesNotExist:
        return (False, "No such club", None)

    club_options = MemberClubOptions.objects.filter(
        club=club,
        user=user,
    ).last()

    if club_options:
        if club_options.allow_membership:
            return (True, "Club is already allowed", club)
        else:
            club_options.delete()

    log_member_change(
        club,
        user.system_number,
        user,
        "User has unblocked club membership",
    )

    ClubLog(
        organisation=club,
        actor=user,
        action=f"{user} has unblocked club membership",
    ).save()

    return (True, None, club)


def _notify_club_of_block(club, user):
    """Send an email to the club notifying them of a membership being blocked"""

    from notifications.views.core import send_cobalt_email_with_template

    # JPG clean-up
    # rule = "members_edit"
    # group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.{rule}")
    # member_editors = rbac_get_users_in_group(group)

    member_editors = rbac_get_users_with_role(f"orgs.members.{club.id}.edit")

    email_body = f"""
        <h1>A user has blocked their membership of your club</h1>
        <p>{user.full_name} ({GLOBAL_ORG} {user.system_number}) was added as a
        member of your club in {GLOBAL_TITLE}, but they have elected to block
        the membership. Typically this should mean that they do not believe that
        they are a member of your club.</p>
        <p>Their membership has been deleted and your club will not be able to
        add them as member while this block is in place.
        <p>If you believe that this person has blocked your club in error,
        please contact them and ask them to allow membership of your club by
        logging in to {GLOBAL_TITLE} and clicking the 'Allow' button on their
        user profile page. This would remove the block and allow a new membership
        to be created for this person.</p>
        <p>The member information your club entered into {GLOBAL_TITLE} about
        this person has been saved as a club contact (see the Club Menu,
        Contacts page). This contact could be converted back into a member if
        the block is removed.</p>
    """

    context = {
        "title": f"Membership blocked by {user.full_name}",
        "email_body": email_body,
        "box_colour": "#007bff",
    }

    for user in member_editors:

        context["name"] = user.first_name

        send_cobalt_email_with_template(
            to_address=user.email,
            context=context,
        )


def _notify_user_of_membership(member_details, user=None):
    """Send an email notification to a registered user that they have been added
    as member by a club, and informing them of the blocking option. Only notify
    registered users and use their profile email (not whatever club email has
    been provided)

    Args:
        member_details (MemberClubDetails): details of the membership
        user (User): user if available
    """

    from notifications.views.core import send_cobalt_email_with_template

    # check for registered user
    if not user:
        try:
            user = User.objects.get(system_number=member_details.system_number)
        except User.DoesNotExist:
            return

    email_body = f"""
        <h1>Membership of {member_details.club.name}</h1>
        <p>{member_details.club.name} has listed you as a club member on {GLOBAL_TITLE},
        with a member type of {member_details.latest_membership.membership_type.name}
        and status of {member_details.get_membership_status_display()}.</p>
        <p>If you are not a member of {member_details.club.name} you can remove this
        membership and block any future attempts to list you as a member of this club.
        This is simple to do from your profile page on {GLOBAL_TITLE} (linked below).</p>
        <p>On this page you can also control if and when you share profile information
        (email address, data of birth and mobile number) with each club you are a member of.
        You can also control whether a club can charge your club membership fees to your
        {BRIDGE_CREDITS} account.</p>
        <p>Please note that blocking a club is not the same as resigning or not renewing a
        legitimate membership. Please contact the club to end a membership in these circumstances.</p>
    """

    context = {
        "title": f"Club membership: {member_details.club.name}",
        "email_body": email_body,
        "box_colour": "#007bff",
        "link": reverse("accounts:user_profile"),
        "link_text": "User Profile",
    }

    send_cobalt_email_with_template(
        to_address=user.email,
        context=context,
    )


def get_members_for_renewal(
    club,
    renewal_parameters,
    form_index=0,
    just_system_number=None,
    stats_to_date=None,
):
    """Return a list of members that match the bulk renewal parameters. Also can return just a single
    member details object for a specified member.

    Args:
        club (Organisation): the club
        renewal_parameters (RenewalParameters): the renewal parameters from the BulkRenewalLineForm
        form_index (int): index of the form in the form set, added to each member
        just_system_number (int): just gets this system number (or None), and returns a single details object
        stats_to_date (dict): a dictionary of statistics to add to

    Returns:
        list: list of augmented MemberClubDetail objects (with allow_auto_pay and form_index)
        dict: a dictionary of statistics
    """

    if stats_to_date:
        stats = stats_to_date.copy()
    else:
        stats = {}

    def init_metrics(metric_list):
        for metric in metric_list:
            if metric not in stats:
                stats[metric] = 0

    def increment_count(metric):
        stats[metric] = stats.get(metric, 0) + 1

    def add_to_total(metric, amount):
        stats[metric] = stats.get(metric, 0) + amount

    init_metrics(
        ["allowing_auto_pay", "no_email", "total_fees", "member_count", "auto_pay_fees"]
    )

    target_end_date = renewal_parameters.start_date - timedelta(days=1)

    if just_system_number:

        member_qs = MemberClubDetails.objects.filter(
            club=club,
            system_number=just_system_number,
        ).select_related(
            "latest_membership",
            "latest_membership__membership_type",
        )

    else:

        member_qs = MemberClubDetails.objects.filter(
            club=club,
            latest_membership__membership_type=renewal_parameters.membership_type,
            membership_status__in=[
                MemberClubDetails.MEMBERSHIP_STATUS_CURRENT,
                MemberClubDetails.MEMBERSHIP_STATUS_DUE,
            ],
            latest_membership__end_date=target_end_date,
        ).select_related(
            "latest_membership",
            "latest_membership__membership_type",
        )

    # check for future memberships for these candiates (cannot renew if one exists)

    system_numbers = [member.system_number for member in member_qs]

    with_future = MemberMembershipType.objects.filter(
        membership_type__organisation=club,
        membership_state=MemberMembershipType.MEMBERSHIP_STATE_FUTURE,
        system_number__in=system_numbers,
    ).values_list("system_number", flat=True)

    member_list = [
        member for member in member_qs if member.system_number not in with_future
    ]

    # NOTE: could use _augment_member_details, then further augment with options, but combining
    # these here avoids a second pass through the member list which might be large

    system_numbers = [member.system_number for member in member_list]

    users = User.objects.filter(system_number__in=system_numbers)
    unreg_users = UnregisteredUser.all_objects.filter(system_number__in=system_numbers)

    # NOTE: Options records are created when someone looks at their profile, so we
    # need to check for people who have blocked (default is allow).

    system_numbers_blocking_auto_pay = MemberClubOptions.objects.filter(
        club=club,
        user__in=users,
        allow_auto_pay=False,
    ).values_list(
        "user__system_number",
        flat=True,
    )

    player_dict = {
        player.system_number: {
            "user_type": f"{GLOBAL_TITLE} User"
            if type(player) is User
            else "Unregistered User",
            "user_or_unreg": player,
            "user_email": player.email if type(player) is User else None,
            "allow_auto_pay": (
                (player.system_number not in system_numbers_blocking_auto_pay)
                and (type(player) is User)
            ),
        }
        for player in chain(users, unreg_users)
    }

    for member in member_list:
        if member.system_number in player_dict:
            member.user_or_unreg = player_dict[member.system_number]["user_or_unreg"]
            member.first_name = member.user_or_unreg.first_name
            member.last_name = member.user_or_unreg.last_name
            member.user_type = player_dict[member.system_number]["user_type"]
            member.allow_auto_pay = player_dict[member.system_number]["allow_auto_pay"]
            member.form_index = form_index
            member.fee = renewal_parameters.fee
            member.auto_pay_date = renewal_parameters.auto_pay_date
            add_to_total("total_fees", member.fee)
            increment_count("member_count")
            if member.allow_auto_pay:
                increment_count("allowing_auto_pay")
                add_to_total("auto_pay_fees", member.fee)

            # Note: this needs to replicate the logic in club_email_for_member
            if member.email:
                member.club_email = member.email
            else:
                member.club_email = player_dict[member.system_number]["user_email"]

            if not member.club_email:
                increment_count("no_email")

    if just_system_number:
        return member_list[0] if len(member_list) > 0 else None
    else:
        return (
            member_list,
            stats,
        )


def _sort_memberships(membership_list, sort_option):
    """Sort a list of memberships by various fields

    Note that the membership_list must be augments by get_outstanding_memberships"""

    if sort_option == "name_desc":
        membership_list.sort(key=lambda x: (x.last_name.lower(), x.first_name.lower()))

    elif sort_option == "name_asc":
        membership_list.sort(
            key=lambda x: (x.last_name.lower(), x.first_name.lower()), reverse=True
        )

    if sort_option == "type_desc":
        membership_list.sort(key=lambda x: x.user_type.lower())

    elif sort_option == "type_asc":
        membership_list.sort(key=lambda x: x.user_type.lower(), reverse=True)

    elif sort_option == "membership_desc":
        membership_list.sort(
            key=lambda x: (
                x.membership_type.name,
                x.start_date,
                x.last_name.lower(),
                x.first_name.lower(),
            )
        )

    elif sort_option == "membership_asc":
        membership_list.sort(
            key=lambda x: (x.last_name.lower(), x.first_name.lower(), x.start_date)
        )
        membership_list.sort(key=lambda x: x.membership_type.name, reverse=True)

    elif sort_option == "due_desc":
        membership_list.sort(
            key=lambda x: (
                x.due_date,
                x.last_name.lower(),
                x.first_name.lower(),
            )
        )

    elif sort_option == "due_asc":
        membership_list.sort(key=lambda x: (x.last_name.lower(), x.first_name.lower()))
        membership_list.sort(key=lambda x: x.due_date, reverse=True)

    elif sort_option == "auto_desc":
        membership_list.sort(
            key=lambda x: (
                x.auto_pay_sort_date,
                x.last_name.lower(),
                x.first_name.lower(),
            )
        )

    elif sort_option == "auto_asc":
        membership_list.sort(key=lambda x: (x.last_name.lower(), x.first_name.lower()))
        membership_list.sort(key=lambda x: x.auto_pay_sort_date, reverse=True)


def get_outstanding_memberships(club, sort_option="name_asc"):
    """Get a list of memberships with outstanding payments for a club

    Args:
        club (Organisation): the club
        sort-option (str): a string specifying the sort field and direction

        The valid fields are name, membership, due and auto. Directions are asc and desc

    Returns:
        list: augmented MemberMembershipType records
        dict: statistics dictionary

    The returned objects are augments with
        first_name (str)
        last_name (str)
        user_type (str): '{GLOABL_TITLE} User' or 'Unregistered User'
        allow_auto_pay (bool)
        user_or_unreg (User or UnregsiteredUser)
    """

    stats = {}

    def init_metrics(metric_list):
        for metric in metric_list:
            if metric not in stats:
                stats[metric] = 0

    def increment_count(metric):
        stats[metric] = stats.get(metric, 0) + 1

    def add_to_total(metric, amount):
        if amount:
            stats[metric] = stats.get(metric, 0) + amount

    init_metrics(["total_fees", "auto_pay_fees"])

    # get the memberships

    memberships = MemberMembershipType.objects.filter(
        membership_type__organisation=club,
        is_paid=False,
        fee__gt=0,
        membership_state__in=[
            MemberMembershipType.MEMBERSHIP_STATE_CURRENT,
            MemberMembershipType.MEMBERSHIP_STATE_DUE,
            MemberMembershipType.MEMBERSHIP_STATE_FUTURE,
        ],
    ).select_related("membership_type")

    # get the related User, UnregisteredUser and MemberClubOption objects

    system_numbers = memberships.values_list("system_number", flat=True)

    users = User.objects.filter(system_number__in=system_numbers)
    unreg = UnregisteredUser.objects.filter(system_number__in=system_numbers)
    member_details = MemberClubDetails.objects.filter(
        club=club, system_number__in=system_numbers
    )

    # build a dictionary of the player data

    system_numbers_blocking_auto_pay = MemberClubOptions.objects.filter(
        club=club,
        user__in=users,
        allow_auto_pay=False,
    ).values_list(
        "user__system_number",
        flat=True,
    )

    club_email_dict = {
        member_detail.system_number: member_detail.email
        for member_detail in member_details
        if member_detail.email
    }

    player_dict = {
        player.system_number: {
            "first_name": player.first_name,
            "last_name": player.last_name,
            "user_or_unreg": player,
            "user_type": f"{GLOBAL_TITLE} User"
            if type(player) == User
            else "Unregistered User",
            "allow_auto_pay": (
                (player.system_number not in system_numbers_blocking_auto_pay)
                and (type(player) is User)
            ),
        }
        for player in chain(users, unreg)
    }

    # augment the memberships

    membership_list = list(memberships)
    for membership in membership_list:
        if membership.system_number in player_dict:
            for key in player_dict[membership.system_number]:
                setattr(membership, key, player_dict[membership.system_number][key])
            add_to_total("total_fees", membership.fee)
            if not membership.auto_pay_date:
                # No auto pay, so sort last
                membership.auto_pay_sort_date = date(2100, 1, 3)
            else:
                if type(membership.user_or_unreg) == User:
                    if membership.allow_auto_pay:
                        add_to_total("auto_pay_fees", membership.fee)
                        membership.auto_pay_sort_date = membership.auto_pay_date
                    else:
                        # blocking, sort after real dates
                        membership.auto_pay_sort_date = date(2100, 1, 1)
                else:
                    # unreg user, sort after blocked
                    membership.auto_pay_sort_date = date(2100, 1, 2)
            if membership.system_number in club_email_dict:
                membership.club_email = club_email_dict[membership.system_number]
            else:
                if type(membership.user_or_unreg) == User:
                    membership.club_email = membership.user_or_unreg.email
                else:
                    membership.club_email = None

    _sort_memberships(membership_list, sort_option)

    return (membership_list, stats)


def get_clubs_with_auto_pay_memberships(date=None):
    """Return a list of clubs that have memberships with auto pay dates at
    or before the specified date (today if none specified).

    Note that a club may be on this list but have no auto payments to make
    once the user permissions have been considered.

    Args:
        date (Date): the auto pay date to find, or today if None

    Returns:
        list: Organisations
    """

    target_date = date if date else timezone.now().date()

    return Organisation.objects.filter(
        full_club_admin=True,
        membershiptype__membermembershiptype__is_paid=False,
        membershiptype__membermembershiptype__auto_pay_date__lte=target_date,
        membershiptype__membermembershiptype__membership_state__in=[
            MemberMembershipType.MEMBERSHIP_STATE_CURRENT,
            MemberMembershipType.MEMBERSHIP_STATE_FUTURE,
            MemberMembershipType.MEMBERSHIP_STATE_DUE,
        ],
    ).distinct()


def get_auto_pay_memberships_for_club(club, date=None):
    """Return a list of memberships that are allowed for auto pay as at the
    specified date (today if none specified) for the club.

    Args:
        club (Organisation): a club whih may or may not have auto pay memberships
        date (Date): the auto pay date to find, or today if None

    Returns:
        list: MemberMembershipTypes augmented with user and member_details
    """

    target_date = date if date else timezone.now().date()

    # get superset of eligible memberships with target auto pay dates

    membership_qs = MemberMembershipType.objects.filter(
        is_paid=False,
        auto_pay_date=target_date,
        membership_type__organisation=club,
        membership_state__in=[
            MemberMembershipType.MEMBERSHIP_STATE_CURRENT,
            MemberMembershipType.MEMBERSHIP_STATE_FUTURE,
            MemberMembershipType.MEMBERSHIP_STATE_DUE,
        ],
    ).select_related("membership_type", "membership_type__organisation")

    # check auto pay permissions

    system_numbers = membership_qs.values_list("system_number", flat=True)

    if len(system_numbers) == 0:
        return None

    allowing = MemberClubOptions.objects.filter(
        club=club,
        user__system_number__in=system_numbers,
        allow_auto_pay=True,
    ).values_list("user__system_number", flat=True)

    # filter the memberships by permissions
    memberships = [
        membership
        for membership in membership_qs
        if membership.system_number in allowing
    ]

    if len(memberships) == 0:
        return None

    # augment with user and membership details

    system_numbers = [membership.system_number for membership in memberships]

    users = User.objects.filter(system_number__in=system_numbers)
    member_details_qs = MemberClubDetails.objects.filter(
        club=club, system_number__in=system_numbers
    )

    user_dict = {user.system_number: user for user in users}
    member_detail_dict = {
        member_details.system_number: member_details
        for member_details in member_details_qs
    }

    for membership in memberships:
        membership.user = user_dict.get(membership.system_number, None)
        membership.member_details = member_detail_dict.get(
            membership.system_number, None
        )

    return memberships
