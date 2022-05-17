""" Script to create cobalt test data """
from django.core.exceptions import SuspiciousOperation

from cobalt.settings import (
    RBAC_EVERYONE,
    TIME_ZONE,
    DUMMY_DATA_COUNT,
    TBA_PLAYER,
    COBALT_HOSTNAME,
)
from accounts.models import User
from django.core.management.base import BaseCommand
from accounts.management.commands.accounts_core import create_fake_user
from forums.models import Post, Comment1, Comment2, LikePost, LikeComment1, LikeComment2
import random
from essential_generators import DocumentGenerator
import datetime
import pytz
from django.utils.timezone import make_aware, now
import glob
import sys
from inspect import currentframe, getframeinfo
from importlib import import_module

TZ = pytz.timezone(TIME_ZONE)
DATA_DIR = "tests/test_data"


class Command(BaseCommand):
    def __init__(self):
        super().__init__()
        self.gen = DocumentGenerator()
        self.id_array = {}

    def parse_csv(self, file):
        """try to sort out the mess Excel makes of CSV files.
        Requires csv files to have the app and model in the first row and
        the fieldnames in the second row."""

        f = open(file, encoding="utf-8")

        all_lines = f.readlines()

        lines = [
            line
            for line in all_lines
            if line.find("#") != 0
            and line.strip() != ""
            and line.replace(",", "").strip() != ""
        ]

        data = []

        try:
            app, model = lines[0].split(",")[:2]
        except ValueError:
            print("\n\nError\n")
            print("Didn't find App, Model on first line of file")
            print(f"File is: {file}")
            print("Line is: %s\n" % lines[0])
            sys.exit()

        try:
            allow_dupes = lines[0].split(",")[3] == "duplicates"
        except (ValueError, IndexError):
            allow_dupes = False

        headers = lines[1]
        header_list = [header.strip() for header in headers.split(",")]

        # loop through records
        for line in lines[2:]:

            # split to parts
            columns = line.split(",")

            # loop through columns
            row = {}
            for i in range(len(header_list)):
                try:
                    if columns[i].strip() != "":
                        row[header_list[i]] = columns[i].strip()
                except IndexError:
                    row[header_list[i]] = None
            data.append(row)

        return app.strip(), model.strip(), data, allow_dupes

    def process_csv(self, csv):
        """do the work on the csv data"""

        app, model, data, allow_dupes = self.parse_csv(csv)
        print(f"App Model is: {app}.{model}\n")

        # special cases
        if app == "accounts" and model == "User":
            self.accounts_user(app, model, data)
            return

        dic = {}
        this_array = None
        for row in data:
            print(row)
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
                        exec_cmd += (
                            f".filter({fkey}=this_array[f'{fapp}.{fmodel}']['{value}'])"
                        )
                    elif key[:2] != "t.":  # exclude time
                        exec_cmd2 = f"module = import_module(f'{app}.models')\nfield_type=module.{model}._meta.get_field('{key}').get_internal_type()"
                        exec(exec_cmd2, globals())
                        if field_type in ["CharField", "TextField"]:  # noqa: F821
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
                print(exc)
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
                        if len(key) > 3 and key[:3] == "id.":  # foreign key
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
                            datetime.datetime(int(yr), int(mt), int(dy), 0, 0),
                            TZ,
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
            dic["TBA"] = User.objects.filter(pk=TBA_PLAYER).first()
            dic["EVERYONE"] = User.objects.filter(pk=RBAC_EVERYONE).first()
            dic["mark"] = User.objects.filter(system_number="620246").first()
            dic["julian"] = User.objects.filter(system_number="518891").first()
        self.id_array["accounts.User"] = dic

    def handle(self, *args, **options):
        if COBALT_HOSTNAME in ["myabf.com.au", "www.myabf.com.au"]:
            raise SuspiciousOperation(
                "Not for use in production. This cannot be used in a production system."
            )

        print("Running add_rbac_test_data")

        try:
            for fname in sorted(glob.glob(f"{DATA_DIR}/*.csv")):
                print("\n#########################################################")
                print(f"Processing: {fname}")
                self.process_csv(fname)

        except KeyboardInterrupt:
            print("\n\nTest data loading interrupted by user\n")
            sys.exit(0)
