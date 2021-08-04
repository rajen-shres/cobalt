from django.core.management.base import BaseCommand

from accounts.models import User
from organisations.models import Organisation, ORGS_RBAC_GROUPS_AND_ROLES
from rbac.core import (
    rbac_get_group_by_name,
    rbac_add_role_to_group,
    rbac_create_group,
    rbac_add_user_to_group,
)
from rbac.models import RBACGroup


class Command(BaseCommand):
    """
    This will check if any generated RBAC groups are missing for an organisation.
    As we add more functionality for clubs we need this to be automated or it will
    be very painful to have to manually update "generated" groups for all the clubs.

    Needs to handle basic and advanced club RBAC

    Gets the definitive list of what should be there from models
    """

    def check_and_fix(self):
        # Loop through all clubs

        clubs = Organisation.objects.filter(type="Club")

        for club in clubs:
            print(f"Checking {club}...")

            # See if basic or advanced

            basic_group = rbac_get_group_by_name(f"{club.rbac_name_qualifier}.basic")
            if basic_group:
                # Basic - has only one group

                print("Club has basic RBAC, adding roles (won't duplicate)...")

                for rule in ORGS_RBAC_GROUPS_AND_ROLES:

                    print(f"{club} - adding {rule} if not there...")

                    # Add roles to group, will do nothing if they already exist
                    rbac_add_role_to_group(
                        group=basic_group,
                        app=ORGS_RBAC_GROUPS_AND_ROLES[rule]["app"],
                        model=ORGS_RBAC_GROUPS_AND_ROLES[rule]["model"],
                        action=ORGS_RBAC_GROUPS_AND_ROLES[rule]["action"],
                        rule_type="Allow",
                        model_id=club.id,
                    )

            else:

                # Advanced - has multiple groups
                print("Club has advanced RBAC...")

                for rule in ORGS_RBAC_GROUPS_AND_ROLES:

                    # See if it exists - do nothing if it does, don't want to change access
                    advanced_group = RBACGroup.objects.filter(
                        name_qualifier=club.rbac_name_qualifier, name_item=rule
                    ).first()
                    if not advanced_group:
                        # create group
                        self.stdout.write(
                            self.style.WARNING(
                                f"{club} group missing. Adding {rule}..."
                            )
                        )

                        advanced_group = RBACGroup(
                            name_qualifier=club.rbac_name_qualifier,
                            name_item=rule,
                            description=f"{ORGS_RBAC_GROUPS_AND_ROLES[rule]['description']} for {club.id} ({club.name})",
                        )
                        advanced_group.save()

                        # Add user
                        rbac_add_user_to_group(club.secretary, advanced_group)

                        rbac_add_role_to_group(
                            group=advanced_group,
                            app=ORGS_RBAC_GROUPS_AND_ROLES[rule]["app"],
                            model=ORGS_RBAC_GROUPS_AND_ROLES[rule]["model"],
                            action=ORGS_RBAC_GROUPS_AND_ROLES[rule]["action"],
                            rule_type="Allow",
                            model_id=club.id,
                        )
                    else:
                        print("Nothing to do")

    def handle(self, *args, **options):

        print("Checking for missing generated RBAC groups for clubs.")
        self.check_and_fix()
        print("Finished.")
