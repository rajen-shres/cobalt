"""Reformat test CV files so you can edit them with the content under the titles"""

import csv
import glob
from shutil import copyfile

from django.core.management.base import BaseCommand


def fix_file(old_file):
    new_file = "/tmp/random_file"
    with open(new_file, "w") as output:

        item_length = {}

        # loop through and find longest line
        input_file = open(old_file)
        reader = csv.reader(input_file)
        for row in reader:
            if row[0] == "#":
                continue
            for index, item in enumerate(row):
                item = item.strip()
                if len(item_length) == index:
                    item_length[index] = 0
                if len(item) > item_length[index]:
                    item_length[index] = len(item)

        with open(old_file) as input_file:
            reader = csv.reader(input_file)
            for row in reader:
                if row[0] == "#":
                    output.write("".join(row))
                    output.write("\n")
                    continue
                for index, item in enumerate(row):
                    item = item.strip()
                    max_len = item_length[index]
                    output.write(f"{item: <{max_len}}, ")
                output.write("\n")

    copyfile(new_file, old_file)


class Command(BaseCommand):
    def handle(self, *args, **options):
        for file in glob.glob("tests/test_data/*.csv"):
            print("Reformatting:", file)
        fix_file(file)
