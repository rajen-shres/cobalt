"""
New file to avoid circulare reference issue on imports

check_system_number(...) moved from accounts/view/admin.py
"""

from accounts.models import User, UnregisteredUser
from masterpoints.views import user_summary


def check_system_number(system_number):
    """Check if system number is valid and also if it is registered already in Cobalt, either as a member or as an
    unregistered user

    Args:
        system_number (int): number to check

    Returns:
        list: is_valid (bool), is_in_use_member (bool), is_in_use_un_reg (bool)

    Returns whether this is a valid (current, active) ABF number, whether we have a user registered with this
    number already or not, whether we have an unregistered user already with this number
    """

    # TODO: Add visitors

    summary = user_summary(system_number)
    is_valid = bool(summary)
    is_in_use_member = User.objects.filter(system_number=system_number).exists()
    is_in_use_un_reg = UnregisteredUser.objects.filter(
        system_number=system_number
    ).exists()

    return is_valid, is_in_use_member, is_in_use_un_reg
