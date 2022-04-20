from django.core.management.base import BaseCommand
from accounts.models import User


class Command(BaseCommand):
    def create_initial_user(
        self, newuser, email, system_number, first, last, about="No info", pic=None
    ):
        if not User.objects.filter(username=newuser).exists():
            user = User.objects.create_user(
                username=newuser,
                email=email,
                password="F1shcake",
                first_name=first,
                last_name=last,
                system_number=system_number,
                about=about,
                pic=pic,
            )
            user.is_superuser = True
            user.is_staff = True
            user.save()
            self.stdout.write(
                self.style.SUCCESS("Successfully created new super user - %s" % newuser)
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("%s user already exists - ok" % newuser)
            )

    def handle(self, *args, **options):
        print("Running createsu.")
        # RBAC Everyone
        self.create_initial_user(
            "EVERYONE", "m@rkguthrie.com", "0", "EVERYONE", "system_account"
        )
        # TBA User for event entry
        self.create_initial_user(
            "TBA",
            "m@rkguthrie.com",
            "1",
            "TBA",
            "",
            "Player entry to be advised",
            "pic_folder/tba.png",
        )

        self.create_initial_user(
            "ABF",
            "nto@abf.com.au",
            "2",
            "ABF",
            "",
            "The Australian Bridge Federation. This account is used to post official ABF announcements.",
            "pic_folder/abf.png",
        )

        self.create_initial_user(
            "Mark",
            "m@rkguthrie.com",
            "620246",
            "Mark",
            "Guthrie",
            "TBA",
            "pic_folder/mark.jpg",
        )

        self.create_initial_user(
            "518891",
            # "julianrfoster@gmail.com",
            "m@rkguthrie.com",
            "518891",
            "Julian",
            "Foster",
            "TBA",
            "pic_folder/julian.jpg",
        )
