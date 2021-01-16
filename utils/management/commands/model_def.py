# generate the headers for the test data CSV files

from accounts.models import User
from django.core.management.base import BaseCommand
from importlib import import_module


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("application", type=str)
        parser.add_argument("model", type=str)

    def handle(self, *args, **options):
        app = options["application"]
        model = options["model"]

        exec_cmd = (
            "module = import_module('%s.models')\nmeta = module.%s._meta.get_fields()"
            % (app, model)
        )

        exec(exec_cmd, globals())

        out = ""
        for item in meta:  # noqa: F821
            if item.concrete:
                out += item.name + ", "
        print(f"{app}, {model}")
        print(out[:-2])
