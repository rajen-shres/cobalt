"""
Core functions for full Club Administration (Release 6.0 and beyond)

All manipulation of the club administration related entities and attributes should be
performed through common functions in this module.

This is intended to provide some level of abstraction of the implementation of the
club administration data model so that future changes can be made more easily.
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

from .models import (
    Organisation,
    MembershipType,
    MemberMembershipType,
    MemberClubDetails,
    MemberClubEmail,
    ClubMemberLog,
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

    Args:
        status (MemberClubDetails.MEMBERSHIP_STATUS): the status (or state)

    Returns:
        str: Description
    """

    membership_status_dict = dict(MemberClubDetails.MEMBERSHIP_STATUS)
    return membership_status_dict.get(status, "Unknown Status")


# -------------------------------------------------------------------------------------
# Data maniputation functions
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
        mark_member_as_deceased(member_detail.club, member_detail.system_number)

    return True


def mark_member_as_deceased(club, system_number, requester=None):
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

    Raises:
        CobaltMemberNotFound: if no member found with this system number
    """

    try:
        member_details = MemberClubDetails.objects.get(
            club=club, system_number=system_number
        )
    except MemberClubDetails.DoesNotExist:
        raise CobaltMemberNotFound(club, system_number)

    # just delete deceased contacts
    if member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_CONTACT:
        member_details.delete()
        return True

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
        member_details.latest_membership.end_date = timezone.now().date()
        member_details.latest_membership.save()

    old_status = member_details.membership_status
    member_details.membership_status = MemberClubDetails.MEMBERSHIP_STATUS_DECEASED
    member_details.save()

    message = f"Status changed from {description_for_status(old_status)} to Deceased"

    log_member_change(
        club,
        system_number,
        requester,
        message,
    )

    return True


def mark_member_as_lapsed(club, system_number, requester=None):
    """Mark the member's current membership as lapsed.
    The end date is set to yesterday. Any future dated due date is reset to yesterday.
    Will fail if the membership status is not current.

    Args:
        club (Organisation): the club
        system_number (int): the member's system number
        requester (User): the user requesting the change

    Returns:
        boolean: success or failure
        string: message or None

    Raises:
        CobaltMemberNotFound: if no member found with this system number
    """

    success, member_details, message = _update_member_status(
        club,
        system_number,
        MemberMembershipType.MEMBERSHIP_STATE_LAPSED,
        [MemberClubDetails.MEMBERSHIP_STATUS_DUE],
        commit=False,
        requester=requester,
    )

    if not success:
        return (False, message)

    if (
        member_details.latest_membership.due_date
        > member_details.latest_membership.end_date
    ):
        member_details.latest_membership.due_date = (
            member_details.latest_membership.end_date
        )
    member_details.latest_membership.save()
    member_details.save()

    return (True, None)


def mark_member_as_resigned(club, system_number, requester=None):
    """Mark the member as resigned.
    The end date is set to yesterday
    The member must be current or current or due

    Args:
        club (Organisation): the club
        system_number (int): the member's system number
        requester (User): the user requesting the change

    Returns:
        boolean: success or failure
        string: message or None

    Raises:
        CobaltMemberNotFound: if no member found with this system number
    """

    success, _, message = _update_member_status(
        club,
        system_number,
        MemberMembershipType.MEMBERSHIP_STATE_RESIGNED,
        [
            MemberClubDetails.MEMBERSHIP_STATUS_CURRENT,
            MemberClubDetails.MEMBERSHIP_STATUS_DUE,
        ],
        requester=requester,
    )

    return (success, message)


def mark_member_as_terminated(club, system_number):
    """Mark the member's current membership as terminated.
    The end date is set to yesterday. Any future dated due date is reset to yesterday.
    Will fail if the membership status is not current or due.

    Args:
        club (Organisation): the club
        system_number (int): the member's system number

    Returns:
        boolean: success or failure
        string: message or None

    Raises:
        CobaltMemberNotFound: if no member found with this system number
    """

    success, _, message = _update_member_status(
        club,
        system_number,
        MemberMembershipType.MEMBERSHIP_STATE_TERMINATED,
        [
            MemberClubDetails.MEMBERSHIP_STATUS_CURRENT,
            MemberClubDetails.MEMBERSHIP_STATUS_DUE,
        ],
    )

    return (success, message)


def _update_member_status(
    club, system_number, new_status, required_statuses=None, commit=True, requester=None
):
    """Private function to handle membership status changes.
    The membership status and the state and end date of the latest membership type are updated
    If a list of required statuses is provide the member must be in one of thise statuses for the
    updates to be made. The member must not be deceased.

    A log record is written if successful (even if not committing the changes)

    Args:
        club (Organisaton): the club
        system_number (int): the member's system number
        new_status (MemberClubDetail.MEMBERSHIP_STATUS): the status to be assigned
        required_statuses (list): list of MemberClubDetail.MEMBERSHIP_STATUS or None
        commit (boolean): save changes?
        requester (User): the user requesting the change

    Returns:
        bool: success or failure
        MemberClubDetails: the member details object (if available)
        string: explanatory message

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

    # if the member is marked as deceased at the user/unreg user level, the status cannot be changed
    # if only marked deceased at the club level, then rely on required_statuses validation
    if member_details.membership_status == MemberClubDetails.MEMBERSHIP_STATUS_DECEASED:
        if check_user_or_unreg_deceased(system_number):
            return (False, member_details, "Member is deceased")

    if required_statuses:
        if member_details.membership_status not in required_statuses:
            return (
                False,
                member_details,
                f"Member is not in a valid status to change to {description_for_status(new_status)}",
            )

    yesterday = timezone.now().date() - timedelta(days=1)
    member_details.latest_membership.end_date = yesterday
    member_details.latest_membership.membership_state = new_status

    old_status = member_details.membership_status
    member_details.membership_status = new_status

    if commit:
        member_details.save()
        member_details.latest_membership.save()

    message = f"Status changed from {description_for_status(old_status)} to {description_for_status(new_status)}"

    log_member_change(
        club,
        system_number,
        requester,
        message,
    )

    return (True, member_details, message)


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
    The member must be in a status of current, due or lapsed.

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

    # JPG Debug
    print(f"renew_membership to {new_end_date}")

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

    if member_details.membership_status != MemberClubDetails.MEMBERSHIP_STATUS_CURRENT:
        return (False, "Member must be current to be extended")

    if new_end_date <= member_details.latest_membership.end_date:
        return (False, "New end date must be later than teh current end date")

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


def add_membership(
    club,
    system_number,
    membership_type,
    annual_fee=None,
    grace_period_days=None,
    is_paid=False,
):
    """Add a new membership to an existing club member.
    The member may have a current membership, or may have lapsed, resigned etc.

    Args:
        club (Organisation): the club
        system_number (int): the member's system number
        membership_type (MembershipType): the membership type to be linked to
        annual_fee (Decimal): optional fee to override the default from the membership type
        grace_period_days (int): optional payment grace period to override the default from the membership type
        is_paid (bool): has the fee been paid

    Returns:
        bool: success
        string: explanatory message or None
    """
    pass


def add_member(
    club,
    system_number,
    membership_type,
    annual_fee=None,
    grace_period_days=None,
    is_paid=False,
):
    """Add a new member and initial membership to a club.
    The person must be an existing user or unregistered user, but not a member of this club.

    Args:
        club (Organisation): the club
        system_number (int): the member's system number
        membership_type (MembershipType): the membership type to be linked to
        annual_fee (Decimal): optional fee to override the default from the membership type
        grace_period_days (int): optional payment grace period to override the default from the membership type
        is_paid (bool): has the fee been paid

    Returns:
        bool: success
        string: explanatory message or None
    """
    pass


# -------------------------------------------------------------------------------------
# Data accessor functions
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
    (ie marked by the support function, nit by a club)

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


def get_club_members(
    club, sort_option="last_desc", exclude_contacts=True, active_only=True
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

    members = members.exclude(
        membership_status=MemberClubDetails.MEMBERSHIP_STATUS_DECEASED
    ).select_related("latest_membership__membership_type")

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
    unreg_users = UnregisteredUser.objects.filter(system_number__in=system_numbers)
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
            system_numner=system_number,
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
