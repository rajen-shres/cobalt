""" Management Commands for accounts """
from accounts.models import User


def create_fake_user(self, system_number, first, last, about="No info", pic=None):
    user = User.objects.filter(username=system_number).first()
    if user:
        self.stdout.write(
            self.style.SUCCESS("%s user already exists - ok" % system_number)
        )
    else:
        user = User.objects.create_user(
            username=system_number,
            #        email="%s@fake.com" % system_number,
            email="m@rkguthrie.com",
            password="F1shcake",
            first_name=first,
            last_name=last,
            system_number=system_number,
            about=about,
            pic=pic,
        )
        user.save()
        self.stdout.write(
            self.style.SUCCESS(
                "Successfully created new user - %s %s(%s)"
                % (first, last, system_number)
            )
        )
    return user
