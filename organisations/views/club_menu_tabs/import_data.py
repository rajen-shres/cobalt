import codecs
import csv

from django.core.exceptions import ValidationError, ImproperlyConfigured
from django.core.validators import validate_email
from django.db.models import Q
from django.shortcuts import render, get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone

from accounts.models import User, UnregisteredUser
from cobalt.settings import GLOBAL_ORG, GLOBAL_MPSERVER
from masterpoints.views import abf_checksum_is_valid
from organisations.decorators import check_club_menu_access
from organisations.forms import CSVUploadForm, MPCForm
from organisations.models import (
    MembershipType,
    ClubLog,
    Organisation,
    MemberMembershipType,
    MemberClubEmail,
)
from organisations.views.club_menu_tabs.members import list_htmx
from utils.views import masterpoint_query


def _csv_pianola(club_member):
    """Pianola specific formatting for CSV files

    Args:
        club_member: list (a row from spreadsheet)

    Returns:
        Bool: True for success, False for failure
        error: message describing error (if there was one)
        item: dict with formatted values

    """

    # Skip visitors, at least for now
    if club_member[21].find("Visitor") >= 0:
        return False, f"{club_member[1]} - skipped visitor", None
    item = {
        "system_number": club_member[1],
        "first_name": club_member[5],
        "last_name": club_member[6],
        "email": club_member[7],
        # "membership_type": club_member[21],
    }

    return True, None, item


def _csv_generic(club_member):
    """formatting for Generic CSV files

    Args:
        club_member: list (a row from spreadsheet)

    Returns:
        Bool: True for success, False for failure
        error: message describing error (if there was one)
        item: dict with formatted values

    """

    item = {
        "system_number": club_member[0],
        "first_name": club_member[1],
        "last_name": club_member[2],
        "email": club_member[3],
    }

    # Allow Membership Type to be specified for each row(member). This overrides the form setting
    if len(club_member) > 4:
        item["membership_type"] = club_member[4]

    return True, None, item


def _cs2_generic(club_member):
    """formatting for Compscore 2 files

    Args:
        club_member: list (a row from spreadsheet)

    Returns:
        Bool: True for success, False for failure
        error: message describing error (if there was one)
        item: dict with formatted values

    """

    item = {
        "system_number": club_member[8],
        "first_name": club_member[1].capitalize(),
        "last_name": club_member[0].capitalize(),
        "email": club_member[7],
    }

    return True, None, item


def _csv_common(item):
    """Common checks for all formats

    Args:
        item: dict

    Returns:
        Bool: True for success, False for failure
        error: message describing error (if there was one)
        item: dict with formatted values

    """

    system_number = item["system_number"]
    first_name = item["first_name"]
    last_name = item["last_name"]
    email = item["email"]
    membership_type = item.get("membership_type")  # None if not set

    system_number = system_number.strip()

    try:
        system_number = int(system_number)
    except ValueError:
        return False, f"{system_number} - invalid {GLOBAL_ORG} Number", None

    # Basic validation

    # TODO: Checking with MPC is too slow. We just validate the checksum
    #  if not check_system_number(system_number):
    if not abf_checksum_is_valid(system_number):
        return False, f"{system_number} - invalid {GLOBAL_ORG} Number", None

    if len(first_name) < 1:
        return False, f"{system_number} - First name missing", None

    if len(last_name) < 1:
        return False, f"{system_number} - Last name missing", None

    if email:
        try:
            validate_email(email)
        except ValidationError:
            return False, f"{system_number} - Invalid email {email}", None

    item = {
        "system_number": system_number,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "membership_type": membership_type,
    }

    return True, None, item


@check_club_menu_access()
def upload_csv_htmx(request, club):
    """Upload CSV"""

    # no files - show form
    if not request.FILES:
        form = CSVUploadForm(club=club)
        return render(
            request, "organisations/club_menu/members/csv_htmx.html", {"form": form}
        )

    form = CSVUploadForm(request.POST, club=club)
    form.is_valid()
    csv_errors = []

    # Get params
    csv_file = request.FILES["file"]
    file_type = form.cleaned_data["file_type"]
    membership_type = form.cleaned_data["membership_type"]
    home_club = form.cleaned_data["home_club"]

    default_membership = get_object_or_404(MembershipType, pk=membership_type)

    # get CSV reader (convert bytes to strings)
    csv_data = csv.reader(codecs.iterdecode(csv_file, "utf-8"))

    # skip header
    next(csv_data, None)

    # Process data
    member_data = []

    for club_member in csv_data:

        # Specific formatting and tests by format
        if file_type == "Pianola":
            rc, error, item = _csv_pianola(club_member)
        elif file_type == "CSV":
            rc, error, item = _csv_generic(club_member)
        elif file_type == "CS2":
            rc, error, item = _cs2_generic(club_member)
        else:
            raise ImproperlyConfigured

        if not rc:
            csv_errors.append(error)
            continue

        # Common checks
        rc, error, item = _csv_common(item)

        if not rc:
            csv_errors.append(error)
            continue

        member_data.append(item)

    added_users, added_unregistered_users, errors = process_member_import(
        club=club,
        member_data=member_data,
        user=request.user,
        origin=file_type,
        default_membership=default_membership,
        home_club=home_club,
        club_specific_email=True,
    )

    # Build results table
    table = render_to_string(
        "organisations/club_menu/members/table_htmx.html",
        {
            "added_users": added_users,
            "added_unregistered_users": added_unregistered_users,
            "errors": errors + csv_errors,
        },
    )

    ClubLog(
        organisation=club,
        actor=request.user,
        action=f"Uploaded member data from CSV file. Type={file_type}",
    ).save()

    return list_htmx(request, table)


@check_club_menu_access()
def import_mpc_htmx(request, club):
    """Import Data from the Masterpoints Centre.

    We connect directly to the MPC to get members for this club.

    Members can be home members or alternate members (members of the club but this
    isn't their home club so ABF and State fees are not charged for them.

    There is no visitor information in the MPC, that happens at the club level.

    """

    if "save" not in request.POST:
        form = CSVUploadForm(club=club)
        return render(
            request,
            "organisations/club_menu/members/mpc_htmx.html",
            {"form": form, "club": club},
        )

    form = MPCForm(request.POST, club=club)
    form.is_valid()

    membership_type = form.cleaned_data["membership_type"]
    default_membership = get_object_or_404(MembershipType, pk=membership_type)

    # Get home club members from MPC
    qry = f"{GLOBAL_MPSERVER}/clubMemberList/{club.org_id}"
    club_members = masterpoint_query(qry)

    member_data = [
        {
            "system_number": club_member["ABFNumber"],
            "first_name": club_member["GivenNames"],
            "last_name": club_member["Surname"],
            "email": club_member["EmailAddress"],
            "membership_type": None,
        }
        for club_member in club_members
    ]

    (
        home_added_users,
        home_added_unregistered_users,
        home_errors,
    ) = process_member_import(
        club=club,
        member_data=member_data,
        user=request.user,
        origin="MPC",
        default_membership=default_membership,
        club_specific_email=False,
        home_club=True,
    )

    # Get Alternate (non-home) club members from MPC
    qry = f"{GLOBAL_MPSERVER}/clubAltMemberList/{club.org_id}"
    club_members = masterpoint_query(qry)

    member_data = [
        {
            "system_number": club_member["ABFNumber"],
            "first_name": club_member["GivenNames"],
            "last_name": club_member["Surname"],
            "email": club_member["EmailAddress"],
        }
        for club_member in club_members
    ]

    alt_added_users, alt_added_unregistered_users, away_errors = process_member_import(
        club=club,
        member_data=member_data,
        user=request.user,
        origin="MPC",
        default_membership=default_membership,
        club_specific_email=False,
        home_club=False,
    )

    errors = home_errors + away_errors
    registered_added = home_added_users + alt_added_users
    unregistered_added = home_added_unregistered_users + alt_added_unregistered_users

    # Build results table
    table = render_to_string(
        "organisations/club_menu/members/table_htmx.html",
        {
            "added_users": registered_added,
            "added_unregistered_users": unregistered_added,
            "errors": errors,
        },
    )

    ClubLog(
        organisation=club,
        actor=request.user,
        action="Imported member data from the Masterpoints Centre",
    ).save()

    return list_htmx(request, table)


def add_member_to_membership(
    club: Organisation,
    club_member: dict,
    user: User,
    default_membership: MembershipType,
    home_club: bool = False,
):
    """Sub process to add a member to the member-membership model. Returns 0 if already there
    or 1 for counting purposes, plus an error or warning if one is found"""

    error = None
    name = f"{club_member['system_number']} - {club_member['first_name']} {club_member['last_name']}"

    # See if we are overriding the membership type
    if club_member["membership_type"]:
        this_membership = MembershipType.objects.filter(
            organisation=club, name=club_member["membership_type"]
        ).first()
        if this_membership:
            default_membership = this_membership
        else:
            return (
                0,
                f"Invalid membership type {club_member['membership_type']} for {name}",
            )

    # Check if already a member (any membership type)
    member_membership = (
        MemberMembershipType.objects.filter(system_number=club_member["system_number"])
        .filter(membership_type__organisation=club)
        .first()
    )

    if member_membership:
        error = f"{name} - Already a member"

        # if other_home_club and home_club:
        #     error = f"{name} - Already a member and has a different home club"
        # elif home_club:
        #     member_membership.home_club = home_club
        #     member_membership.save()
        return 0, error

    # check for other home clubs before setting this as the users home club
    other_home_club = MemberMembershipType.objects.filter(
        system_number=club_member["system_number"]
    ).exists()

    if home_club and other_home_club:
        error = f"{name} - Added but already has a home club"
        home_club = False

    MemberMembershipType(
        membership_type=default_membership,
        system_number=club_member["system_number"],
        last_modified_by=user,
        home_club=home_club,
    ).save()
    return 1, error


def process_member_import(
    club: Organisation,
    member_data: list,
    user: User,
    origin: str,
    default_membership: MembershipType,
    home_club: bool = False,
    club_specific_email: bool = False,
):
    """Common function to process a list of members

    Args:
        default_membership: Which membership to add this user to. Can be overridden at the row level
        club_specific_email: Is this email specific to this club? True for 'club' sources like Pianola, False for MPC
        home_club: Is this the home club for this user
        origin: Where did we get this data from?
        user: Logged in user who is making this change
        member_data: list of data
        club: Club object

    """

    # counters
    added_users = 0
    added_unregistered_users = 0
    errors = []

    # loop through members
    for club_member in member_data:

        # See if we have an actual user for this
        user_match = User.objects.filter(
            system_number=club_member["system_number"]
        ).first()

        if user_match:
            added, error = add_member_to_membership(
                club, club_member, user, default_membership, home_club
            )
            added_users += added
        else:
            # See if we have an unregistered user already
            un_reg = UnregisteredUser.objects.filter(
                system_number=club_member["system_number"]
            ).first()

            if not un_reg:
                # Create a new unregistered user

                # Check if this email should be added to user or just this club
                email = None if club_specific_email else club_member["email"]

                UnregisteredUser(
                    system_number=club_member["system_number"],
                    first_name=club_member["first_name"],
                    last_name=club_member["last_name"],
                    email=email,
                    origin=origin,
                    last_updated_by=user,
                    added_by_club=club,
                ).save()

            # add to club email list if required - don't override if already present
            if (
                club_specific_email
                and club_member["email"]
                and not MemberClubEmail.objects.filter(
                    organisation=club,
                    system_number=club_member["system_number"],
                ).exists()
            ):
                MemberClubEmail(
                    organisation=club,
                    system_number=club_member["system_number"],
                    email=club_member["email"],
                ).save()

            added, error = add_member_to_membership(
                club, club_member, user, default_membership, home_club
            )

            added_unregistered_users += added

        if error:
            errors.append(error)

    return added_users, added_unregistered_users, errors
