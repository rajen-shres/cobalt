"""Reformat test CV files so you can edit them with the content under the titles"""

import csv
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
            for index, item in enumerate(row):
                item = item.strip()
                if len(item_length) == index:
                    item_length[index] = 0
                if len(item) > item_length[index]:
                    item_length[index] = len(item)

        print(item_length)

        # loop through and write out
        input_file = open(old_file)
        reader = csv.reader(input_file)
        for row in reader:
            line = ""
            for index, item in enumerate(row):
                item = item.strip()
                max_len = item_length[index]
                print(item, max_len)
                output.write(f"{item: <{max_len}}, ")
                line += f"{item: <{max_len}}, "
            print(line)
            output.write("\n")

        input_file.close()

    copyfile(new_file, old_file)


class Command(BaseCommand):
    def handle(self, *args, **options):
        fix_file("tests/test_data/aa.csv")
