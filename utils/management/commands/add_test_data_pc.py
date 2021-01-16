""" Script to create cobalt test data """

from cobalt.settings import RBAC_EVERYONE, TIME_ZONE
from accounts.models import User
from events.models import CongressMaster
from django.core.management.base import BaseCommand
from accounts.management.commands.accounts_core import create_fake_user
from forums.management.commands.forums_core import create_forum
from organisations.management.commands.orgs_core import create_org
from rbac.management.commands.rbac_core import (
    create_RBAC_action,
    create_RBAC_default,
    create_RBAC_admin_group,
    create_RBAC_admin_tree,
)
from rbac.core import (
    rbac_add_user_to_admin_group,
    rbac_add_role_to_admin_group,
    rbac_create_group,
    rbac_add_user_to_group,
    rbac_add_role_to_group,
)
from payments.core import update_account, update_organisation
from payments.models import StripeTransaction
from forums.models import Post, Comment1, Comment2, LikePost, LikeComment1, LikeComment2
from organisations.models import MemberOrganisation
from rbac.models import RBACModelDefault
from events.models import Congress, Event, Session
import random
from essential_generators import DocumentGenerator
import datetime
import pytz
from django.utils.timezone import make_aware, now, utc
from importlib import import_module
import glob
import sys
from inspect import currentframe, getframeinfo

TZ = pytz.timezone(TIME_ZONE)
DATA_DIR = "c:\\test-data"


class Command(BaseCommand):
    def __init__(self):
        super().__init__()
        self.gen = DocumentGenerator()
        self.id_array = {}

    def add_comments(self, post, user_list):
        """ add comments to a forum post """

        liker_list = list(set(user_list) - set([post.author]))
        sample_size = random.randrange(int(len(liker_list) * 0.8))
        for liker in random.sample(liker_list, sample_size):
            like = LikePost(post=post, liker=liker)
            like.save()
        for c1_counter in range(random.randrange(10)):
            text = self.random_paragraphs()
            c1 = Comment1(post=post, text=text, author=random.choice(user_list))
            c1.save()
            liker_list = list(set(user_list) - set([c1.author]))
            sample_size = random.randrange(int(len(liker_list) * 0.8))
            for liker in random.sample(liker_list, sample_size):
                like = LikeComment1(comment1=c1, liker=liker)
                like.save()
            post.comment_count += 1
            post.save()
            for c2_counter in range(random.randrange(10)):
                text = self.random_paragraphs()
                c2 = Comment2(
                    post=post, comment1=c1, text=text, author=random.choice(user_list)
                )
                c2.save()
                post.comment_count += 1
                post.save()
                c1.comment1_count += 1
                c1.save()
                liker_list = list(set(user_list) - set([c2.author]))
                sample_size = random.randrange(int(len(liker_list) * 0.8))
                for liker in random.sample(liker_list, sample_size):
                    like = LikeComment2(comment2=c2, liker=liker)
                    like.save()

    def random_paragraphs(self):
        """ generate a random paragraph """
        text = self.gen.paragraph()
        for counter in range(random.randrange(10)):
            text += "\n\n" + self.gen.paragraph()
        return text

    def random_sentence(self):
        """ generate a random sentence """
        return self.gen.sentence()

    def random_paragraphs_with_stuff(self):
        """ generate a more realistic rich test paragraph with headings and pics """

        sizes = [
            ("400x500", "400px"),
            ("400x300", "400px"),
            ("700x300", "700px"),
            ("900x500", "900px"),
            ("200x200", "200px"),
            ("800x200", "800px"),
            ("500x400", "500px"),
        ]

        text = self.gen.paragraph()
        for counter in range(random.randrange(10)):
            type = random.randrange(8)
            if type == 5:  # no good reason
                text += "<h2>%s</h2>" % self.gen.sentence()
            elif type == 7:
                index = random.randrange(len(sizes))
                text += (
                    "<p><img src='https://source.unsplash.com/random/%s' style='width: %s;'><br></p>"
                    % (sizes[index][0], sizes[index][1])
                )
            else:
                text += "<p>%s</p>" % self.gen.paragraph()
        return text

    def parse_csv(self, file):
        """ try to sort out the mess Excel makes of CSV files.
            Requires csv files to have the app and model in the first row and
            the fieldnames in the second row. """

        f = open(file)

        lines = f.readlines()

        data = []

        try:
            app, model = lines[0].split(",")[:2]
        except ValueError:
            print("\n\nError\n")
            print("Didn't find App, Model on first line of file")
            print("File is: %s" % file)
            print("Line is: %s\n" % lines[0])
            sys.exit()

        try:
            if lines[0].split(",")[3] == "duplicates":
                allow_dupes = True
            else:
                allow_dupes = False
        except (ValueError, IndexError):
            allow_dupes = False

        headers = lines[1]
        header_list = []

        # take column names from header
        for header in headers.split(","):
            header_list.append(header.strip())

        # loop through records
        for line in lines[2:]:

            # skip empty rows
            if (
                line.find("#") == 0
                or line.strip() == ""
                or line.strip().replace(",", "") == ""
            ):
                continue

            # split to parts
            columns = line.split(",")

            # loop through columns
            row = {}
            for i in range(len(header_list)):
                try:
                    if not columns[i].strip() == "":
                        row[header_list[i]] = columns[i].strip()
                except IndexError:
                    row[header_list[i]] = None
            data.append(row)

        return (app.strip(), model.strip(), data, allow_dupes)

    def process_csv(self, csv):
        """ do the work on the csv data """
        app, model, data, allow_dupes = self.parse_csv(csv)
        print(f"App Model is: {app}.{model}\n")

        # special cases
        if app == "accounts" and model == "User":
            self.accounts_user(app, model, data)
        else:
            # default
            dic = {}
            this_array = None
            for row in data:
                # see if already present
                exec_cmd = (
                    "module = import_module('%s.models')\ninstance = module.%s.objects"
                    % (app, model)
                )

                for key, value in row.items():
                    if value and key != "id" and key[:2] != "d." and key[:2] != "m.":
                        if key[:3] == "id.":  # foreign key

                            parts = key.split(".")

                            fkey = parts[1]
                            fapp = parts[2]
                            fmodel = parts[3]
                            this_array = self.id_array
                            exec_cmd += f".filter({fkey}=this_array[f'{fapp}.{fmodel}']['{value}'])"
                        elif key[:2] != "t.":  # exclude time
                            exec_cmd2 = f"module = import_module(f'{app}.models')\nfield_type=module.{model}._meta.get_field('{key}').get_internal_type()"
                            exec(exec_cmd2, globals())
                            if (
                                field_type == "CharField"  # noqa: F821
                                or field_type == "TextField"  # noqa: F821
                            ):  # noqa: F821
                                exec_cmd += f".filter({key}='{value}')"
                            else:
                                exec_cmd += f".filter({key}={value})"
                exec_cmd += ".first()"

                local_array = {"this_array": this_array}
                try:
                    exec(exec_cmd, globals(), local_array)
                except (KeyError, NameError) as exc:
                    print("\n\nError\n")
                    print(str(exc))
                    for block in self.id_array:
                        for key2, val2 in self.id_array[block].items():
                            print(block, key2, val2)
                    print("\nStatement was:")
                    print(exec_cmd)
                    sys.exit()
                instance = local_array["instance"]

                # that was hard, now check it
                if instance and not allow_dupes:
                    print("already present: %s" % instance)
                else:
                    exec_cmd = (
                        "module = import_module('%s.models')\ninstance = module.%s()"
                        % (app, model)
                    )
                    local_array = {}
                    exec(exec_cmd, globals(), local_array)
                    instance = local_array["instance"]

                    if not instance:
                        print("\n\nError\n")
                        print(f"Failed to create instance of {app}.{model}")
                        print(f"Processing file: {csv}\n")
                        frameinfo = getframeinfo(currentframe())
                        print(
                            "Error somewhere above: ",
                            frameinfo.filename,
                            frameinfo.lineno,
                            "\n",
                        )
                        sys.exit()
                    for key, value in row.items():
                        try:
                            value = value.replace("^", ",")
                        except AttributeError:
                            pass
                        if key != "id" and key[:2] != "t.":
                            if len(key) > 3:
                                if key[:3] == "id.":  # foreign key
                                    parts = key.split(".")
                                    fkey = parts[1]
                                    fapp = parts[2]
                                    fmodel = parts[3]
                                    try:
                                        val = self.id_array[f"{fapp}.{fmodel}"][value]
                                    except KeyError:
                                        print("\n\nError\n")
                                        print(row)
                                        print(
                                            f"Foreign key not found: {fapp}.{fmodel}: {value}"
                                        )
                                        print(
                                            f"Check that the file with {app}.{model} has id {value} and that it is loaded before this file.\n"
                                        )
                                        sys.exit()
                                    setattr(instance, fkey, val)
                                else:
                                    setattr(instance, key, value)
                            else:
                                setattr(instance, key, value)
                        if key[:2] == "t.":
                            field = key[2:]
                            adjusted_date = now() - datetime.timedelta(days=int(value))
                            datetime_local = adjusted_date.astimezone(TZ)
                            setattr(instance, field, datetime_local)
                        if key[:2] == "d.":
                            field = key[2:]
#                            dy, mt, yr = value.split("/")
                            val_str = "%s" % value
                            yr = val_str[:4]
                            mt = val_str[4:6]
                            dy = val_str[6:8]

                            this_date = make_aware(
                                datetime.datetime(int(yr), int(mt), int(dy), 0, 0), TZ,
                            )
                            setattr(instance, field, this_date)
                        if key[:2] == "m.":
                            field = key[2:]
                            dt = datetime.datetime.strptime(value, "%H:%M").time()
                            setattr(instance, field, dt)
                    instance.save()
                    print("Added: %s" % instance)
                # add to dic if we have an id field
                if "id" in row.keys():
                    dic[row["id"]] = instance

            self.id_array[f"{app}.{model}"] = dic

    def accounts_user(self, app, model, data):
        dic = {}
        for row in data:
            if "about" not in row:
                row["about"] = None
            if "pic" not in row:
                row["pic"] = None

            user = create_fake_user(
                self,
                row["system_number"],
                row["first_name"],
                row["last_name"],
                row["about"],
                row["pic"],
            )
            dic[row["id"]] = user
            dic["EVERYONE"] = User.objects.filter(pk=RBAC_EVERYONE).first()
            dic["mark"] = User.objects.filter(system_number="620246").first()
            dic["julian"] = User.objects.filter(system_number="518891").first()
        self.id_array["accounts.User"] = dic

    def handle(self, *args, **options):
        print("Running add_rbac_test_data")

        for fname in sorted(glob.glob(DATA_DIR + "/*.csv")):
            print("\n#########################################################")
            print("Processing: %s" % fname)
            self.process_csv(fname)

        # create dummy Posts
        print("\nCreating dummy forum posts")
        print("Running", end="", flush=True)
        for post_counter in range(10):

            user_list = list(self.id_array["accounts.User"].values())
            user_list.remove(self.id_array["accounts.User"]["EVERYONE"])

            post = Post(
                forum=random.choice(list(self.id_array["forums.Forum"].values())),
                title=self.random_sentence(),
                text=self.random_paragraphs_with_stuff(),
                author=random.choice(user_list),
            )
            post.save()
            print(".", end="", flush=True)
            self.add_comments(post, user_list)
        print("\n")
