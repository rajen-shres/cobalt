import codecs
import csv
from datetime import datetime
import logging
import re

from django.core.exceptions import ValidationError, ImproperlyConfigured
from django.core.validators import validate_email, RegexValidator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import render, get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone

from accounts.models import (
    User,
    UnregisteredUser,
    NextInternalSystemNumber,
)
from cobalt.settings import GLOBAL_ORG, GLOBAL_MPSERVER
from masterpoints.views import abf_checksum_is_valid
from organisations.club_admin_core import (
    add_contact_with_system_number,
    add_member,
    change_membership,
    get_member_details,
    convert_contact_to_member,
    log_member_change,
    MEMBERSHIP_STATES_ACTIVE,
)
from organisations.decorators import check_club_menu_access
from organisations.forms import (
    CSVUploadForm,
    MPCForm,
    CSVContactUploadForm,
)
from organisations.models import (
    MemberClubDetails,
    MembershipType,
    ClubLog,
    Organisation,
    MemberMembershipType,
)
from organisations.views.club_menu_tabs.members import list_htmx as members_list_htmx
from organisations.views.club_menu_tabs.contacts import list_htmx as contacts_list_htmx
from utils.views.general import masterpoint_query


# Mapping for generic CSV member imports
GENERIC_MEMBER_MAPPING = {
    "system_number": {"csv_col": 0, "type": "sysnum", "required": True},
    "first_name": {"csv_col": 1, "required": True},
    "last_name": {"csv_col": 2, "required": True},
    "email": {"csv_col": 3, "type": "email"},
    "membership_type": {"csv_col": 4, "type": "str", "len": 20, "opt_column": True},
    "address1": {"csv_col": 5, "len": 100, "opt_column": True},
    "address2": {"csv_col": 6, "len": 100, "opt_column": True},
    "state": {"csv_col": 7, "type": "str", "len": 3, "opt_column": True},
    "postcode": {"csv_col": 8, "type": "str", "len": 10, "opt_column": True},
    "preferred_phone": {"csv_col": 9, "type": "str", "len": 15, "opt_column": True},
    "other_phone": {"csv_col": 10, "type": "str", "len": 15, "opt_column": True},
    "dob": {"csv_col": 11, "type": "date", "opt_column": True, "no_future": None},
    "club_membership_number": {"csv_col": 12, "opt_column": True},
    "joined_date": {"csv_col": 13, "type": "date", "opt_column": True},
    "left_date": {"csv_col": 14, "type": "date", "opt_column": True},
    "emergency_contact": {"csv_col": 15, "opt_column": True},
    "notes": {"csv_col": 16, "opt_column": True},
}

# Mapping for generic CSV member imports
GENERIC_CONTACT_MAPPING = {
    "first_name": {"csv_col": 0, "required": True},
    "last_name": {"csv_col": 1, "required": True},
    "email": {"csv_col": 2, "type": "email", "opt_column": True},
    "system_number": {"csv_col": 3, "type": "sysnum", "opt_column": True},
    "address1": {"csv_col": 4, "len": 100, "opt_column": True},
    "address2": {"csv_col": 5, "len": 100, "opt_column": True},
    "state": {"csv_col": 6, "type": "str", "len": 3, "opt_column": True},
    "postcode": {"csv_col": 7, "type": "str", "len": 10, "opt_column": True},
    "preferred_phone": {"csv_col": 8, "type": "str", "len": 15, "opt_column": True},
    "other_phone": {"csv_col": 9, "type": "str", "len": 15, "opt_column": True},
    "dob": {"csv_col": 10, "type": "date", "opt_column": True, "no_future": None},
    "emergency_contact": {"csv_col": 11, "opt_column": True},
    "notes": {"csv_col": 12, "opt_column": True},
}

# Mapping for PIANOLA CSV member imports
PIANOLA_MAPPING = {
    "system_number": {"csv_col": 1, "type": "sysnum", "required": True},
    "first_name": {"csv_col": 5, "required": True},
    "last_name": {"csv_col": 6, "required": True},
    "email": {"csv_col": 7, "type": "email"},
    "address1": {"csv_col": 10, "type": "concat", "other": 11, "len": 100},
    "address2": {"csv_col": 12, "type": "concat", "other": 13, "len": 100},
    "state": {"csv_col": 14, "type": "str", "len": 3},
    "postcode": {"csv_col": 15, "type": "str", "len": 10},
    "dob": {"csv_col": 20, "type": "date", "no_future": None},
    "membership_type": {"csv_col": 21, "type": "str", "len": 20},
    "club_membership_number": {"csv_col": 0},
    "joined_date": {"csv_col": 22, "type": "date"},
    "left_date": {
        "csv_col": 26,
        "type": "date",
    },
    "emergency_contact": {"csv_col": 30},
    "notes": {"csv_col": 29},
}

# Mapping for PIANOLA CSV contacts imports, same as for members, but system number optional
PIANOLA_CONTACT_MAPPING = {
    "system_number": {"csv_col": 1, "type": "sysnum"},
    "first_name": {"csv_col": 5, "required": True},
    "last_name": {"csv_col": 6, "required": True},
    "email": {"csv_col": 7, "type": "email"},
    "address1": {"csv_col": 10, "type": "concat", "other": 11, "len": 100},
    "address2": {"csv_col": 12, "type": "concat", "other": 13, "len": 100},
    "state": {"csv_col": 14, "type": "str", "len": 3},
    "postcode": {"csv_col": 15, "type": "str", "len": 10},
    "dob": {"csv_col": 20, "type": "date", "no_future": None},
    "emergency_contact": {"csv_col": 30},
    "notes": {"csv_col": 29},
}

# Mapping for Compscore CSV member imports
COMPSCORE_MEMBER_MAPPING = {
    "system_number": {"csv_col": 8, "type": "sysnum", "required": True},
    "first_name": {"csv_col": 1, "required": True, "case": "cap"},
    "last_name": {"csv_col": 0, "required": True, "case": "cap"},
    "email": {"csv_col": 7, "type": "email"},
    "address1": {"csv_col": 2, "type": "str", "len": 100},
    "address2": {"csv_col": 3, "type": "str", "len": 100},
    "postcode": {"csv_col": 4, "type": "str", "len": 10},
    "preferred_phone": {"csv_col": 5, "type": "str", "len": 15},
    "other_phone": {"csv_col": 6, "type": "str", "len": 15},
    "emergency_contact": {"csv_col": 10},
    "notes": {"csv_col": 11},
    "dob": {"csv_col": 12, "type": "date", "no_future": None},
    "club_membership_number": {"csv_col": 14},
}

DATE_FORMATS = [
    "%d/%m/%Y",
    "%d/%m/%y",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%d/%m/%Y %H:%M",
    "%d/%m/%y %H:%M",
    "%x",
    "%c",
]

# post code ranges to states
# Note: needs to be searched in order to pick up exceptions
POSTCODE_RANGES = [
    (200, 221, "ACT"),
    (800, 899, "NT"),
    (1000, 1999, "NSW"),
    (2600, 2617, "ACT"),
    (2900, 2906, "ACT"),
    (2913, 2914, "ACT"),
    (2000, 2899, "NSW"),
    (3586, 3586, "NSW"),
    (3644, 3644, "NSW"),
    (3707, 3707, "NSW"),
    (3000, 3999, "VIC"),
    (4000, 4999, "QLD"),
    (5000, 5999, "SA"),
    (6000, 6999, "WA"),
    (7000, 7999, "TAS"),
    (8000, 8999, "VIC"),
    (9000, 9999, "QLD"),
]


def state_from_postcode(postcode):
    """Returns the three leter Australian state string for a given postcode

    Args:
        postcode (str): some postcode string

    Returns:
        str: state string or None
    """

    if not postcode:
        return None

    try:
        pc_int = int(postcode)
    except ValueError:
        return None

    for low, high, state_str in POSTCODE_RANGES:
        if low <= pc_int <= high:
            return state_str

    return None


def _map_csv_to_columns(mapping, csv, strict=False):
    """Use a mapping specification to build a dictionary of import values
    from a list of column values from a csv file row.

    This performs type conversion (from str) and validation of data types and required values,
    as specified in the mapping. Malformed values are ignore unless in a required field or in
    strict mode.

    The mapping specification is a dictionary keyed by ClubMemberDetails attribute name.
    Each value is a dictionary with the following key:values pairs:
        csv_col : int, 0 relative column number to use (required)
        type : str, a valid type used for conversion and validation (optional, defaults to str)
            sysnum = an ABF number (int with a valid checksum)
            str = a string
            int = an integer
            email = a validly formed email address
            mobile = a validly formed mobile number (non digits are stripped)
            phone = a validly formed phone number (non digits are stripped)
            date = a date in one of the supported formats
            concat = concatenation of two str columns (second column specified by 'other')
        required : bool, is a value required (optional, defaults to false)
        len : int, the length to truncate to for str or concat types (optional)
        other : int, the 0 relative index for the second column in a concatenation (required if concat)
        opt_column : bool, if true the column could be omitted. If optional columns are allowed, all columns
            after the first optional column must also be optional
        case : str, specifying case conversion for str values:
            cap : capitalise
            upper : upper
        date_formats : list of date format strings for interpreting date fields
        no_future : if this key exists (any value), it error if it is a date field in the future

    Args:
        mapping (dict): a mapping specification dictionary
        csv (list): a list of teh data columns from a csv row
        strict (bool): error if any field fails conversion or validation

    Returns:
        Bool: True for success, False for failure
        error: message describing error (if there was one)
        item: dict with formatted values
    """

    def _smart_concat(part1, part2):
        if part1 and part2:
            return f"{part1}, {part2}"
        elif part1:
            return part1
        elif part2:
            return part2
        else:
            return ""

    item = {}
    for attr_name in mapping:

        spec = mapping[attr_name]

        def _str_value(old_str):
            # return a correcly converted string value
            if "len" in spec:
                new_str = old_str[: spec["len"]]
            else:
                new_str = old_str

            if "case" in spec:
                if spec["case"] == "cap":
                    new_str = new_str.capitalize()
                elif spec["case"] == "upper":
                    new_str = new_str.upper()
            return new_str

        # skip optional columns if not there
        if spec.get("opt_column", False) and spec["csv_col"] >= len(csv):
            continue

        # check for required value
        if spec.get("required", False) and not csv[spec["csv_col"]]:
            return (
                False,
                f"{attr_name} expected in column {spec['csv_col']}",
                None,
            )

        if csv[spec["csv_col"]] or spec.get("type", None) == "concat":
            # type checking
            source = csv[spec["csv_col"]]
            if "type" in spec:

                if spec["type"] == "sysnum":
                    # a system number, must be an int with a valid checksum

                    try:
                        system_number = int(source)
                    except ValueError:
                        if spec.get("required", False) or strict:
                            return (
                                False,
                                f"Invalid {GLOBAL_ORG} Number in column {spec['csv_col']} '{source}'",
                                None,
                            )
                        continue

                    # TODO: Checking with MPC is too slow. We just validate the checksum
                    if not abf_checksum_is_valid(system_number):
                        if spec.get("required", False) or strict:
                            return (
                                False,
                                f"Invalid {GLOBAL_ORG} Number in column {spec['csv_col']} '{source}'",
                                None,
                            )
                        else:
                            continue

                    item[attr_name] = system_number

                elif spec["type"] == "str":
                    # a string with optional length limit and case treatment

                    item[attr_name] = _str_value(source)

                elif spec["type"] == "concat":
                    # combine two strings with optional length limit

                    other = csv[spec["other"]]
                    concat = _smart_concat(source, other)
                    if concat:
                        if "len" in spec:
                            item[attr_name] = concat[: spec["len"]]
                        else:
                            item[attr_name] = concat

                    elif spec.get("required", False):
                        return (
                            False,
                            f"{attr_name} expected in columns {spec['csv_col']} or {spec['other']}",
                            None,
                        )

                elif spec["type"] == "int":
                    # an integer

                    try:
                        item[attr_name] = int(source)
                    except ValueError:
                        if spec.get("required", False) or strict:
                            return (
                                False,
                                f"Invalid {attr_name} ({spec['type']}) in column {spec['csv_col']} '{source}'",
                                None,
                            )

                elif spec["type"] == "date":
                    # a date, in a variety of formats

                    date_obj = None
                    for date_format in (
                        spec["date_formats"] if "date_formats" in spec else DATE_FORMATS
                    ):
                        try:
                            date_obj = datetime.strptime(source, date_format).date()
                            break
                        except ValueError:
                            date_obj = None
                    if date_obj:
                        if "no_future" in spec and date_obj > timezone.now().date():
                            if spec.get("required", False) or strict:
                                return (
                                    False,
                                    f"Invalid {attr_name} ({spec['type']}) in column {spec['csv_col']} '{source}' - future date not allowed",
                                    None,
                                )
                        else:
                            item[attr_name] = date_obj
                    else:
                        if spec.get("required", False) or strict:
                            return (
                                False,
                                f"Invalid {attr_name} ({spec['type']}) in column {spec['csv_col']} '{source}'",
                                None,
                            )

                elif spec["type"] == "email":
                    # an email address

                    try:
                        validate_email(source)
                        item[attr_name] = source
                    except ValidationError:
                        if spec.get("required", False) or strict:
                            return (
                                False,
                                f"Invalid {attr_name} ({spec['type']}) in column {spec['csv_col']} '{source}'",
                                None,
                            )

                elif spec["type"] == "mobile":
                    # an Australian mobile number

                    digits_only = re.sub(r"\D", "", source)
                    mobile_regex = r"^04\d{8}$"
                    if re.match(mobile_regex, digits_only):
                        item[attr_name] = digits_only
                    else:
                        if spec.get("required", False) or strict:
                            return (
                                False,
                                f"Invalid {attr_name} ({spec['type']}) in column {spec['csv_col']} '{source}'",
                                None,
                            )

                elif spec["type"] == "phone":
                    # a phone number

                    digits_only = re.sub(r"\D", "", source)
                    phone_regex = r"^\+?1?\d{9,15}$"
                    if re.match(phone_regex, digits_only):
                        item[attr_name] = digits_only
                    else:
                        if spec.get("required", False) or strict:
                            return (
                                False,
                                f"Invalid {attr_name} ({spec['type']}) in column {spec['csv_col']} '{source}'",
                                None,
                            )

                else:
                    # unknown type, treat as a string
                    item[attr_name] = _str_value(source)

            else:
                # no type specified (ie string)
                item[attr_name] = _str_value(source)

    return (True, None, item)


def _augment_member_details(club, system_number, new_details, overwrite=False):
    """Augment an existing MemberClubDetails record with values from a dictionary.

    By default existing values are not overwriten
    The MemberClubDetails must exist, and is saved on exit

    Returns:
        bool: have any updates been made
    """

    member_details = MemberClubDetails.objects.get(
        club=club, system_number=system_number
    )

    updated = False
    for attr_name in new_details:
        # do not update with falsey values
        if new_details[attr_name]:
            try:
                old_value = getattr(member_details, attr_name)
                if not old_value or overwrite:
                    if old_value != new_details[attr_name]:
                        setattr(member_details, attr_name, new_details[attr_name])
                        updated = True
            except (AttributeError, TypeError):
                pass

    if updated:
        member_details.save()

    return updated


def _csv_pianola_phone_numbers(club_member, item):
    """Handle processing for Pianola phone number columns for an import row

    Pianola has two phone number columns (column 8 'Phone number' and
    column 9 'Mobile Number'). Either may be blank. One may have '(P)'
    indicating preferred phone number.

    Args:
        club_member (list): a row from spreadsheet
        item (dict): previously mapped values

    Returns:
        Bool: True for success, False for failure
        error: message describing error (if there was one)
        item: dict with mapped values
    """

    if len(club_member) < 10:
        return (
            False,
            "Phone number columns missing",
            item,
        )

    MARKER = "(P)"
    MAX_LEN = 15

    pianola_phone = club_member[8]
    phone = pianola_phone.replace(MARKER, "")[:MAX_LEN] if pianola_phone else None
    pianola_mobile = club_member[9]
    mobile = pianola_mobile.replace(MARKER, "")[:MAX_LEN] if pianola_mobile else None

    if pianola_mobile and pianola_mobile.find(MARKER) != -1:
        item["preferred_phone"] = mobile
        if pianola_phone:
            # ignore the marker being against both, should not happen
            # if it does, will use mobile as preferred
            item["other_phone"] = phone
    elif pianola_phone and pianola_phone.find(MARKER) != -1:
        item["preferred_phone"] = phone
        if pianola_mobile:
            item["other_phone"] = mobile
    else:
        # no marked preferred phone
        if pianola_mobile:
            item["preferred_phone"] = mobile
            if pianola_phone:
                item["other_phone"] = phone
        elif pianola_phone:
            item["preferred_phone"] = phone

    return (True, None, item)


def _csv_pianola(club_member, contacts=False):
    """Pianola specific formatting for CSV files

    Args:
        club_member (list): a row from spreadsheet
        overwrite (bool): overwrite existign values with non-blank
        contacts (bool): process only visitor rows

    Returns:
        Bool: True for success, False for failure
        error: message describing error (if there was one)
        item: dict with formatted values

    """

    if contacts:

        if club_member[21].find("Visitor") >= 0:
            success, error, item = _map_csv_to_columns(
                PIANOLA_CONTACT_MAPPING, club_member
            )
        else:
            return False, f"{club_member[1]} - skipped non-visitor", None

    else:

        if club_member[21].find("Visitor") >= 0:
            return False, f"{club_member[1]} - skipped visitor", None
        else:
            success, error, item = _map_csv_to_columns(PIANOLA_MAPPING, club_member)

    if success:
        return _csv_pianola_phone_numbers(club_member, item)
    else:
        return (success, error, item)


def _csv_generic(club_member, contacts=False):
    """formatting for Generic CSV files

    Args:
        club_member: list (a row from spreadsheet)
        contacts (bool): use contacts mapping

    Returns:
        Bool: True for success, False for failure
        error: message describing error (if there was one)
        item: dict with formatted values

    """

    if contacts:
        return _map_csv_to_columns(GENERIC_CONTACT_MAPPING, club_member)
    else:
        return _map_csv_to_columns(GENERIC_MEMBER_MAPPING, club_member)


def _csv_compscore(club_member):
    """formatting for Compscore 2/3 files
    Populates state code from the postcode

    Args:
        club_member: list (a row from spreadsheet)

    Returns:
        Bool: True for success, False for failure
        error: message describing error (if there was one)
        item: dict with formatted values

    """
    success, error, item = _map_csv_to_columns(COMPSCORE_MEMBER_MAPPING, club_member)

    if "postcode" in item:
        state_str = state_from_postcode(item["postcode"])
        if state_str:
            item["state"] = state_str

    return (success, error, item)


@check_club_menu_access()
def upload_csv_htmx(request, club):
    """Import members from a CSV file"""

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
    overwrite = form.cleaned_data["overwrite"]

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
            rc, error, item = _csv_compscore(club_member)
        else:
            raise ImproperlyConfigured

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
        overwrite=overwrite,
        home_club=home_club,
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

    return members_list_htmx(request, table)


@check_club_menu_access()
def import_mpc_htmx(request, club):
    """Import Data from the Masterpoints Centre.

    We connect directly to the MPC to get members for this club.

    Members can be home members or alternate members (members of the club but this
    isn't their home club so ABF and State fees are not charged for them).

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

    member_data = []

    for club_member in club_members:

        # Check if email address is valid. Some in the MPC are not
        email_address = club_member["EmailAddress"]
        try:
            validate_email(email_address)
        except ValidationError:
            email_address = ""

        try:
            system_no_as_int = int(club_member["ABFNumber"])
        except ValueError:
            continue

        member_data.append(
            {
                "system_number": system_no_as_int,
                "first_name": club_member["GivenNames"],
                "last_name": club_member["Surname"],
                "email": email_address,
                "membership_type": None,
            }
        )

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
        overwrite=True,
        home_club=True,
    )

    # JPG to do - include overwrite option in UI?

    # Build results table
    table = render_to_string(
        "organisations/club_menu/members/table_htmx.html",
        {
            "added_users": home_added_users,
            "added_unregistered_users": home_added_unregistered_users,
            "errors": home_errors,
        },
    )

    ClubLog(
        organisation=club,
        actor=request.user,
        action="Imported member data from the Masterpoints Centre",
    ).save()

    return members_list_htmx(request, table)


def add_member_to_membership(
    club: Organisation,
    club_member: dict,
    user: User,
    default_membership: MembershipType,
    overwrite: bool = False,
    home_club: bool = False,
    is_registered_user: bool = True,
):
    """Sub process to add a member to the club. Returns 0 if already there
    or 1 for counting purposes, plus an error or warning if one is found

    Args:
        user (User): logged in user making the request

    """

    name = f"{club_member['system_number']} - {club_member['first_name']} {club_member['last_name']}"

    # See if we are overriding the membership type
    if "membership_type" in club_member and club_member["membership_type"]:
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

    # check whether a member already (active or otherwise, or contact)
    member_details = get_member_details(club, club_member["system_number"])

    if member_details and member_details.membership_status in MEMBERSHIP_STATES_ACTIVE:
        updated = _augment_member_details(
            club,
            club_member["system_number"],
            club_member,
            overwrite=overwrite,
        )

        if (
            member_details.latest_membership.membership_type != default_membership
            and overwrite
        ):
            # member exists, but the membership type has changed!
            success, message = change_membership(
                club,
                club_member["system_number"],
                default_membership,
                user,
            )
            if success:
                updated = True
            else:
                return 0, f"{name} - {message}"

        if not updated:
            return 0, f"{name} - Already an active member"
        else:
            return 1, f"{name} - Already an active member, details updated"

    if member_details:

        if (
            member_details.membership_status
            == MemberClubDetails.MEMBERSHIP_STATUS_CONTACT
        ):
            # contact, so convert

            success, message = convert_contact_to_member(
                club,
                club_member["system_number"],
                club_member["system_number"],
                default_membership,
                user,
            )

        else:
            # has a non-current membership with this club, so change to default
            success, message = change_membership(
                club,
                club_member["system_number"],
                default_membership,
                user,
            )

    else:
        # create the member details and membership records

        # calculate a reasonable start date, based on joined date (if provided)
        start_date = None
        if "joined_date" in club_member:
            club_year_start = club.last_renewal_date
            if club_member["joined_date"] >= club_year_start:
                start_date = club_member["joined_date"]
            else:
                start_date = club_year_start

        success, message = add_member(
            club,
            club_member["system_number"],
            is_registered_user,
            default_membership,
            user,
            start_date=start_date,
        )

    # update membership details with MCP email address and other values unless there is already one

    if success:
        _augment_member_details(
            club,
            club_member["system_number"],
            club_member,
            overwrite=overwrite,
        )

    if success:
        return 1, f"{name} - {message}" if message else None
    else:
        return 0, message


def process_member_import(
    club: Organisation,
    member_data: list,
    user: User,
    origin: str,
    default_membership: MembershipType,
    overwrite: bool,
    home_club: bool = False,
):
    """Common function to process a list of members

    Args:
        club: Club object
        member_data: list of data
        user: Logged in user who is making this change
        origin: Where did we get this data from?
        default_membership: Which membership to add this user to. Can be overridden at the row level
        home_club: Is this the home club for this user
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
                club, club_member, user, default_membership, overwrite, home_club
            )
            added_users += added
        else:
            # See if we have an unregistered user already
            un_reg = UnregisteredUser.objects.filter(
                system_number=club_member["system_number"]
            ).first()

            if not un_reg:
                # Create a new unregistered user

                UnregisteredUser(
                    system_number=club_member["system_number"],
                    first_name=club_member["first_name"],
                    last_name=club_member["last_name"],
                    origin=origin,
                    last_updated_by=user,
                    added_by_club=club,
                ).save()

            added, error = add_member_to_membership(
                club,
                club_member,
                user,
                default_membership,
                overwrite=overwrite,
                home_club=home_club,
                is_registered_user=False,
            )

            added_unregistered_users += added

        if error:
            errors.append(error)

    return added_users, added_unregistered_users, errors


@check_club_menu_access()
def contact_upload_csv_htmx(request, club):
    """Upload contacts from CSV"""

    # no files - show form
    if not request.FILES:
        form = CSVContactUploadForm()
        return render(
            request, "organisations/club_menu/contacts/csv_htmx.html", {"form": form}
        )

    form = CSVContactUploadForm(request.POST)
    form.is_valid()
    csv_errors = []

    # Get params
    csv_file = request.FILES["file"]
    file_type = form.cleaned_data["file_type"]
    overwrite = form.cleaned_data["overwrite"]

    # get CSV reader (convert bytes to strings)
    csv_data = csv.reader(codecs.iterdecode(csv_file, "utf-8"))

    # skip header
    next(csv_data, None)

    # Process data
    contact_data = []

    for club_member in csv_data:

        # Specific formatting and tests by format
        if file_type == "Pianola":
            rc, error, item = _csv_pianola(club_member, contacts=True)
        elif file_type == "CSV":
            rc, error, item = _csv_generic(club_member, contacts=True)
        elif file_type == "CS2":
            rc, error, item = _csv_compscore(club_member)
        else:
            raise ImproperlyConfigured

        if not rc:
            csv_errors.append(error)
            continue

        contact_data.append(item)

    added_contacts, updated_contacts, errors = process_contact_import(
        club=club,
        contact_data=contact_data,
        user=request.user,
        origin=file_type,
        overwrite=overwrite,
    )

    # Build results table
    table = render_to_string(
        "organisations/club_menu/contacts/table_htmx.html",
        {
            "added_contacts": added_contacts,
            "updated_contacts": updated_contacts,
            "errors": errors + csv_errors,
        },
    )

    ClubLog(
        organisation=club,
        actor=request.user,
        action=f"Uploaded contact data from CSV file. Type={file_type}",
    ).save()

    return contacts_list_htmx(request, table)


def process_contact_import(
    club: Organisation,
    contact_data: list,
    user: User,
    origin: str,
    overwrite: bool,
):
    """Process a list of imported contacts

    Args:
        club (Organisation): the club
        contact_data (list): list of contact details (dictionaries keyed by attribute name)
        user (User): processing user
        origin (str): file type being uploaded
        overwrite (bool): overwrite existing values with new

    Returns:
        int: number of contacts added
        int: number of existing contacts updated
        errors: list of error/warning messages
    """

    # counters
    added_contacts = 0
    updated_contacts = 0
    errors = []

    # loop through members
    for contact in contact_data:

        error = None
        existing_contact = False

        if "system_number" in contact:

            # check whether this system number is already a club member or contact

            check_member = get_member_details(club, contact["system_number"])
            if check_member:

                # do not process if a member
                if (
                    check_member.membership_status
                    != MemberClubDetails.MEMBERSHIP_STATUS_CONTACT
                ):
                    errors.append(
                        f"{GLOBAL_ORG} Number {contact['system_number']} is already a member"
                    )
                    continue

                # continue for an existing contact to allow for updates to details
                existing_contact = True
                error = f"{GLOBAL_ORG} Number {contact['system_number']} is already a contact"

            else:

                # check whether this person is already on the system
                user_match = User.objects.filter(
                    system_number=contact["system_number"]
                ).first()

                if not user_match:
                    un_reg = UnregisteredUser.objects.filter(
                        system_number=contact["system_number"]
                    ).first()

                    if not un_reg:
                        #  create an unregistered user

                        UnregisteredUser(
                            system_number=contact["system_number"],
                            first_name=contact["first_name"],
                            last_name=contact["last_name"],
                            origin=origin,
                            last_updated_by=user,
                            added_by_club=club,
                        ).save()

        else:
            # no system number, create an unregistered user with an internal system number

            with transaction.atomic():

                # create a new unregistered user with an internal system number
                unreg_user = UnregisteredUser()
                unreg_user.system_number = NextInternalSystemNumber.next_available()
                unreg_user.first_name = contact["first_name"]
                unreg_user.last_name = contact["last_name"]
                unreg_user.origin = "CSV"
                unreg_user.internal_system_number = True
                unreg_user.added_by_club = club
                unreg_user.last_updated_by = user
                unreg_user.save()

                contact["system_number"] = unreg_user.system_number

        # either a user or un_reg user now exists, so create (if required) and augment the contact details

        if not existing_contact:
            add_contact_with_system_number(club, contact["system_number"])

        updated = _augment_member_details(
            club,
            contact["system_number"],
            contact,
            overwrite=overwrite,
        )

        # log it
        if existing_contact:
            if updated:
                log_member_change(
                    club,
                    contact["system_number"],
                    user,
                    "Contact updated (csv upload)",
                )
                updated_contacts += 1
                error += ", details updated"
            errors.append(error)

        else:
            log_member_change(
                club,
                contact["system_number"],
                user,
                "Contact created (csv upload)",
            )
            added_contacts += 1

    return added_contacts, updated_contacts, errors
