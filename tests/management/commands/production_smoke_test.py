from django.core.management.base import BaseCommand

from tests.simple_selenium_parser import simple_selenium_parser


class Command(BaseCommand):
    def add_arguments(self, parser):

        parser.add_argument("--password", help="password for user")
        parser.add_argument("--silent", help="don't display any output")
        parser.add_argument("--script", help="script to execute")
        parser.add_argument("--browser", help="Browser - default is chrome")
        parser.add_argument(
            "--base_url", help="Base url for server e.g. http://127.0.0.1:8088"
        )
        parser.add_argument(
            "--show", help="Specify a value to run browser in the foreground"
        )

    def handle(self, *args, **options):

        show = options["show"]
        browser = options["browser"]
        base_url = options["base_url"]
        password = options["password"]
        script = options["script"]
        silent = options["silent"]

        if not base_url:
            base_url = "https://test.myabf.com.au"

        simple_selenium_parser(
            script,
            base_url=base_url,
            password=password,
            show=show,
            browser=browser,
            silent=silent,
        )
