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

from django.utils import timezone

from accounts.models import (
    User,
    UnregisteredUser,
    UserAdditionalInfo,
)
from cobalt.settings import GLOBAL_TITLE

from notifications.models import Recipient

from .models import (
    Organisation,
    MembershipType,
    MemberMembershipType,
    MemberClubDetails,
    MemberClubEmail,
    ClubMemberLog,
    MemberClubTag,
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


def member_details_description(member_details):
    """A comprehensive descriptive string of the type, status and relevant dates"""

    period = f"from {member_details.latest_membership.start_date:%d %b %Y}"
    if member_details.latest_membership.end_date:
        period += f" to {member_details.latest_membership.end_date:%d %b %Y}"

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

    paid_until = None
    if (
        member_details.latest_membership.paid_until_date
        and member_details.latest_membership.paid_until_date
        != member_details.latest_membership.end_date
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
        if member_details.latest_membership.due_date:
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


# -------------------------------------------------------------------------------------
#   Data accessor functions
#
#   Key functions for accessing membership data are:
#       get_member_details : get a single member's details
#       get_club_members : get all club members
# -------------------------------------------------------------------------------------


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
        # just return teh current membership

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


def get_member_system_numbers(club, target_list=None):
    """Return a list of system numbers for current members,
    optionally constarined within a list of system numbers

    Args:
        club (Organisation): the club
        target_list (list): system numbers to narrow the query
    """

    qs = MemberClubDetails.objects.filter(
        club=club,
        membership_status__in=MEMBERSHIP_STATES_ACTIVE,
    )

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
    """Returns a list of member detail objects for the specified club, augmented with
    the names and types (user, unregistered, contact).

    Args:
        club (Organisation): the club
        sort_option (string): sort column and order
        exclude_contacts (boolean): exclude contacts from the list
        active_only (boolean): include only current and due members

    Returns:
        list: augmented club member details in the specified order
    """

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

    members = members.select_related("latest_membership__membership_type")

    # augment with additional details
    return _augment_member_details(members, sort_option=sort_option)


def _augment_member_details(member_qs, sort_option="last_desc"):
    """Augments a query set of members with user/unregistered user details

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
        else:
            member.first_name = "Unknown"
            member.last_name = "Unknown"
            member.user_type = "Unknown Type"
            member.user_or_unreg_id = None

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


def get_club_contact_list(
    club,
):
    """Return a list of system numbers of club contacts"""

    return MemberClubDetails.objects.filter(
        club=club,
        membership_status=MemberClubDetails.MEMBERSHIP_STATUS_CONTACT,
    ).values_list("system_number", flat=True)


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
    return _augment_contact_details(contacts, sort_option=sort_option)


def _augment_contact_details(contact_qs, sort_option="last_desc"):
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
        else:
            contact.first_name = "Unknown"
            contact.last_name = "Unknown"
            contact.user_type = "Unknown Type"
            contact.user_or_unreg_id = None
            contact.internal = True

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

    augmented_list = _augment_contact_details(member_qs, None)

    if len(augmented_list) == 0:
        return None
    else:
        return augmented_list[0]


def club_email_for_member(club, system_number):
    """Return an email address to be used by a club for a member (or None), and
    whether the email has bounced. The email could be club specific or from the user
    record. No email address will be returned for a deceased member. A User level email
    will not be returned for a contact with no club specific email.

    Args:
        club (Organisation): the club
        system_number (int): member's system number

    Returns:
        string: email address or None if not specified
        bool: email has hard bounced
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
        return (None, False)

    if member_details.email:
        return (member_details.email, member_details.email_hard_bounce)

    if member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_CONTACT:
        # a contact, but no email (!), so don't look for a User record
        return (None, False)

    # no club specific email, so check for a user record
    try:
        user = User.objects.get(system_number=system_number)
    except User.DoesNotExist:
        return (None, False)

    # check for additional infor for bounce status
    additional_info = UserAdditionalInfo.objects.filter(user=user).last()

    return (user.email, additional_info.email_hard_bounce if additional_info else False)


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

    if member_details.is_active_status:
        return (True, None)

    return (False, "Member must be in an active status to mark as lapsed")


def can_mark_as_resigned(member_details):
    """Can the member validly be marked as resigned?"""

    if (
        member_details.is_active_status
        or member_details.membership_status
        == MemberClubDetails.MEMBERSHIP_STATUS_LAPSED
    ):
        return (True, None)

    return (False, "Member must be in an active status to mark as resigned")


def can_mark_as_terminated(member_details):
    """Can the member validly be marked as terminated?"""

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

    if member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_DECEASED:
        return (False, "Member is already marked as deceased")

    if member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_CONTACT:
        return (False, "Contacts cannot be marked as deceased")

    return (True, None)


def can_mark_as_paid(member_details):
    """Can the member validly be marked as paid?"""

    if not (
        member_details.is_active_status
        or member_details.membership_status
        == MemberClubDetails.MEMBERSHIP_STATUS_LAPSED
    ):
        return (False, "Member must be in an active state to be marked as paid")

    today = timezone.now().date()

    if (
        member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_LAPSED
        and member_details.end_date < today
    ):
        return (False, "Lapsed members cannot pay after the end date")

    if member_details.latest_membership.is_paid:
        return (False, "Membership is already paid")

    return (True, None)


def can_extend_membership(member_details):
    """Can the member validly be extended?"""

    if member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_CURRENT:
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

    if member_details.membership_status != MemberClubDetails.MEMBERSHIP_STATUS_CONTACT:

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


def mark_player_as_deceased(system_number):
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
        _mark_member_as_deceased(member_detail.club, member_detail.system_number)

    return True


def add_member(
    club,
    system_number,
    membership_type,
    requester,
    fee=None,
    start_date=None,
    end_date=None,
    due_date=None,
    is_paid=True,
    email=None,
):
    """Add a new member and initial membership to a club.
    The person must be an existing user or unregistered user, but not a member of this club.

    Args:
        club (Organisation): the club
        system_number (int): the member's system number
        membership_type (MembershipType): the membership type to be linked to
        annual_fee (Decimal): optional fee to override the default from the membership type
        start_date (Date): the start date of the membership
        end_date (Date): the end date of the membership
        due_date (Date): due date of payment
        is_paid (bool): has the fee been paid
        email (str): club specific email

    Returns:
        bool: success
        string: explanatory message or None
    """

    today = timezone.now().date()

    # build the new membership record
    new_membership = MemberMembershipType()
    new_membership.system_number = system_number
    new_membership.last_modified_by = requester
    new_membership.membership_type = membership_type
    new_membership.fee = fee if fee else membership_type.annual_fee
    new_membership.start_date = start_date if start_date else today
    if membership_type.does_not_renew:
        new_membership.end_date = None
    else:
        new_membership.end_date = end_date if end_date else club.current_end_date
    if is_paid or new_membership.fee == 0:
        new_membership.due_date = None
        new_membership.paid_until_date = new_membership.end_date
        new_membership.membership_state = MemberMembershipType.MEMBERSHIP_STATE_CURRENT
    else:
        new_membership.due_date = (
            due_date
            if due_date
            else new_membership.start_date
            + timedelta(days=membership_type.grace_period_days)
        )
        new_membership.paid_until_date = new_membership.start_date - timedelta(days=1)
        new_membership.membership_state = MemberMembershipType.MEMBERSHIP_STATE_DUE

    # last minute validatation

    if new_membership.start_date > today:
        return (False, "Start date cannot be in the future")

    if new_membership.start_date and new_membership.end_date:
        if new_membership.start_date > new_membership.end_date:
            return (False, "End date must be after start date")

    new_membership.save()

    # create a new member details record

    member_details = MemberClubDetails()
    member_details.system_number = system_number
    member_details.club = club
    member_details.latest_membership = new_membership

    if email:
        member_details.email = email

    # JPG to do : defaulting of details from User record?

    member_details.membership_status = new_membership.membership_state
    member_details.joined_date = today

    member_details.save()

    # and log it
    message = f"Joined club ({membership_type.name})"

    if is_paid and new_membership.paid_until_date:
        message += f", paid to {new_membership.paid_until_date.strftime('%d-%m-%Y')}"

    log_member_change(
        club,
        system_number,
        requester,
        message,
    )

    return (True, message)


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
            # JPG to do - should an auto due date be created?
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
    """Mark a member as paid. Sets the paid until to be the end date, changes the status
    and removes the due date. Logs the update.
    """

    member_details.latest_membership.state = (
        MemberMembershipType.MEMBERSHIP_STATE_CURRENT
    )
    member_details.latest_membership.due_date = None
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

    return (True, "Membership information deleted. Deatils saved as a contact")


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


def renew_membership(
    club,
    system_number,
    new_end_date,
    new_fee,
    new_due_date,
    is_paid=False,
    requester=None,
):
    """Extend the members current membership to a new end date.

    Args:
        club (Organisation): the club
        system_number (int): the member's system number
        new_end_date (Date): the extended end date
        new_fee (Decimal): the fee associated with the renewal
        new_due_date (Date): the fee payment due date
        is_paid (bool): has the new fee been paid
        requester (User): the user requesting the change

    Returns:
        bool: success
        string: explanatory message or None

    Raises:
        CobaltMemberNotFound: if no member found with this system number
    """

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

    permitted_action, message = can_perform_action("extend", member_details)
    if not permitted_action:
        return (False, message)

    if new_end_date <= member_details.latest_membership.end_date:
        return (False, "New end date must be later than the current end date")

    old_end_date = member_details.latest_membership.end_date
    member_details.latest_membership.end_date = new_end_date
    member_details.latest_membership.fee = new_fee
    member_details.latest_membership.due_date = new_due_date
    if is_paid:
        member_details.latest_membership.paid_until_date = new_end_date
        member_details.latest_membership.membership_state = (
            MemberMembershipType.MEMBERSHIP_STATE_CURRENT
        )
    else:
        member_details.latest_membership.membership_state = (
            MemberMembershipType.MEMBERSHIP_STATE_DUE
        )
    member_details.membership_status = member_details.latest_membership.membership_state

    member_details.latest_membership.save()
    member_details.save()

    log_member_change(
        club,
        system_number,
        requester,
        f"{member_details.latest_membership.membership_type.name} membership extended from "
        + f"{old_end_date.strftime('%d-%m-%Y')} to {new_end_date.strftime('%d-%m-%Y')}",
    )

    if is_paid:
        log_member_change(
            club,
            system_number,
            requester,
            f"Membership marked as paid to {new_end_date.strftime('%d-%m-%Y')}",
        )

    return (True, "Membership extended")


def change_membership(
    club,
    system_number,
    membership_type,
    requester,
    fee=None,
    start_date=None,
    end_date=None,
    due_date=None,
    is_paid=False,
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

    # get the member data and latest membership
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

    permitted_action, message = can_perform_action("change", member_details)

    if not permitted_action:
        return (False, message)

    # build the new membership record
    new_membership = MemberMembershipType()
    new_membership.system_number = system_number
    new_membership.last_modified_by = requester
    new_membership.membership_type = membership_type
    new_membership.fee = fee if fee else membership_type.annual_fee
    new_membership.start_date = start_date if start_date else today
    if membership_type.does_not_renew:
        new_membership.end_date = None
    else:
        new_membership.end_date = end_date if end_date else club.current_end_date
    if is_paid or new_membership.fee == 0:
        new_membership.due_date = None
        new_membership.paid_until_date = new_membership.end_date
        new_membership.membership_state = MemberMembershipType.MEMBERSHIP_STATE_CURRENT
    else:
        new_membership.due_date = (
            due_date
            if due_date
            else new_membership.start_date
            + timedelta(days=membership_type.grace_period_days)
        )
        new_membership.paid_until_date = new_membership.start_date - timedelta(days=1)
        new_membership.membership_state = MemberMembershipType.MEMBERSHIP_STATE_DUE

    # last minute validatation

    if new_membership.start_date > today:
        return (False, "Start date cannot be in the future")

    if new_membership.start_date and new_membership.end_date:
        if new_membership.start_date > new_membership.end_date:
            return (False, "End date must be after start date")

    # update the member record and the previous membership record
    new_membership.save()

    if member_details.latest_membership.membership_state in MEMBERSHIP_STATES_ACTIVE:
        member_details.latest_membership.membership_state = (
            MemberMembershipType.MEMBERSHIP_STATE_ENDED
        )
        member_details.latest_membership.end_date = (
            new_membership.start_date - timedelta(days=1)
        )
        member_details.latest_membership.save()

    member_details.latest_membership = new_membership
    member_details.membership_status = new_membership.membership_state
    member_details.save()

    # and log it
    message = f"Membership changed to {membership_type.name}"

    if is_paid and new_membership.paid_until_date:
        message += f", paid to {new_membership.paid_until_date.strftime('%d-%m-%Y')}"

    log_member_change(
        club,
        system_number,
        requester,
        message,
    )

    return (True, message)


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
    member_details.joined_date = membership.start_date

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
        elif is_user and user.share_with_clubs:
            member_details.email = user.email
            additional_info = UserAdditionalInfo.objects.fileter(user=user).last()
            if additional_info:
                member_details.email_hard_bounce = additional_info.email_hard_bounce
                member_details.email_hard_bounce_reason = (
                    additional_info.email_hard_bounce_reason
                )
                member_details.email_hard_bounce_date = (
                    additional_info.email_hard_bounce_date
                )

        if is_user and user.share_with_clubs:
            member_details.dob = user.dob
            member_details.mobile = user.mobile

    member_details.save()


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
                f"Unable to conver MemberMembershipType {membership} for {club}, no matching user"
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
    is_paid=True,
):
    """Convert a club contact to a member with the supplied parameters.

    The contact may be a User, UnregisteredUser with an ABF number or an UnregisteredUser with
    an internal system number.

    Args:
        club (Organisation): the club
        system_number (int): the member's system number
        contact (MemberClubDetails): the contact member record
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
    """

    today = timezone.now().date()

    member_details = MemberClubDetails.objects.get(
        club=club,
        system_number=old_system_number,
    )

    contact_unreg_user = UnregisteredUser.all_objects.filter(
        system_number=old_system_number
    ).last()

    # check if converting an internal system number unreg user contact
    if contact_unreg_user and contact_unreg_user.internal_system_number:

        # check whether the new system number is already in use
        check_user = User.objects.filter(
            system_number=system_number,
        ).last()

        if check_user:
            # system number is in use by a registered user
            contact_unreg_user.delete()

        else:
            check_unreg = UnregisteredUser.objects.filter(
                system_number=system_number,
            ).last()

            if check_unreg:
                # system number is in use by an unreg user
                contact_unreg_user.delete()

            else:
                # system number not in use, so convert to unreg user
                contact_unreg_user.system_number = system_number
                contact_unreg_user.internal_system_number = False
                contact_unreg_user.save()

        # now have either a user or unreg user with the new system number
        # so update the contact and any other uses of the old system number
        member_details.system_number = system_number

        _replace_internal_system_number(old_system_number, system_number)

    # build the new membership record
    new_membership = MemberMembershipType()
    new_membership.system_number = system_number
    new_membership.last_modified_by = requester
    new_membership.membership_type = membership_type
    new_membership.fee = fee if fee else membership_type.annual_fee
    new_membership.start_date = start_date if start_date else today
    if membership_type.does_not_renew:
        new_membership.end_date = None
    else:
        new_membership.end_date = end_date if end_date else club.current_end_date
    if is_paid or new_membership.fee == 0:
        new_membership.due_date = None
        new_membership.paid_until_date = new_membership.end_date
        new_membership.membership_state = MemberMembershipType.MEMBERSHIP_STATE_CURRENT
    else:
        new_membership.due_date = (
            due_date
            if due_date
            else new_membership.start_date
            + timedelta(days=membership_type.grace_period_days)
        )
        new_membership.paid_until_date = new_membership.start_date - timedelta(days=1)
        new_membership.membership_state = MemberMembershipType.MEMBERSHIP_STATE_DUE

    # last minute validatation

    if new_membership.start_date > today:
        return (False, "Start date cannot be in the future")

    if new_membership.start_date and new_membership.end_date:
        if new_membership.start_date > new_membership.end_date:
            return (False, "End date must be after start date")

    new_membership.save()

    # update the member detail record (the old contact object)

    member_details.latest_membership = new_membership
    member_details.membership_status = new_membership.membership_state
    member_details.joined_date = today

    member_details.save()

    # and log it
    message = f"Contact converted to member ({membership_type.name})"

    if is_paid and new_membership.paid_until_date:
        message += f", paid to {new_membership.paid_until_date.strftime('%d-%m-%Y')}"

    log_member_change(
        club,
        system_number,
        requester,
        message,
    )

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
