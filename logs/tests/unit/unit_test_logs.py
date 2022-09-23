from logs.models import Log
from logs.views import log_event
from tests.test_manager import CobaltTestManagerIntegration


def _log_event_helper(
    manager, user, severity, source, sub_source, message=None, request=None
):
    """Helper for testing log event"""

    if not message:
        message = f"{user} - {source} - {sub_source} - {severity}"

    log_event(user, severity, source, sub_source, message, request)

    last_log_event = Log.objects.all().last()

    output = f"""This test will crash if it fails, any output means success.

    <h4>log entry</h4>
    <dl>
        <dt>Event Date</dt>
        <dd>{last_log_event.event_date}</dd>
        <dt>User</dt>
        <dd>{last_log_event.user}</dd>
        <dt>Source</dt>
        <dd>{last_log_event.source}</dd>
        <dt>Sub-Source</dt>
        <dd>{last_log_event.sub_source}</dd>
        <dt>Severity</dt>
        <dd>{last_log_event.severity}</dd>
        <dt>Message</dt>
        <dd>{last_log_event.message}</dd>
        <dt>IP</dt>
        <dd>{last_log_event.ip}</dd>
    </dl>

    """

    manager.save_results(
        status=True,
        test_name=message,
        test_description="Test for event logging",
        output=output,
    )


class LogTests:
    """Unit tests for the logging functions. We want logging to cope with any bad data it is sent."""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager

    def good_data(self):
        """Tests for it working"""

        # Pass user=User
        for status in Log.SeverityCodes:
            _log_event_helper(
                self.manager,
                self.manager.alan,
                status,
                "Test 1",
                "Simple Test - User Object",
            )

        # Pass user=str
        for status in Log.SeverityCodes:
            _log_event_helper(
                self.manager,
                "User as String",
                status,
                "Test 1",
                "Simple Test - User String",
            )

        # Create a fake request
        response = self.manager.client.get("/")
        request = response.wsgi_request

        # Pass user=User with request
        for status in Log.SeverityCodes:
            _log_event_helper(
                self.manager,
                self.manager.alan,
                status,
                "Test 1",
                "With Request - User Object",
                request=request,
            )

        # Pass user=str with request
        for status in Log.SeverityCodes:
            _log_event_helper(
                self.manager,
                "User as String",
                status,
                "Test 1",
                "With Request - User String",
                request=request,
            )

    def bad_data(self):
        """Tests for it coping"""

        # Create a fake request
        response = self.manager.client.get("/")
        request = response.wsgi_request

        # Bad status
        _log_event_helper(
            self.manager, "String User", "Invalid", "Errors", "Bad Status user str"
        )
        _log_event_helper(
            self.manager,
            "String User",
            "Invalid",
            "Errors",
            "Bad Status user str with Request",
            request=request,
        )
        _log_event_helper(
            self.manager, self.manager.alan, "Invalid", "Errors", "Bad Status"
        )
        _log_event_helper(
            self.manager,
            self.manager.alan,
            "Invalid",
            "Errors",
            "Bad Status with Request",
            request=request,
        )

        # Long Bad status
        _log_event_helper(
            self.manager,
            "String User",
            "Invalid and also very long",
            "Errors",
            "Usr Str Bad Long Status",
        )
        _log_event_helper(
            self.manager,
            "String User",
            "Invalid and also very long",
            "Errors",
            "Usr Str Bad Long Status with Request",
            request=request,
        )
        _log_event_helper(
            self.manager,
            self.manager.alan,
            "Invalid and also very long",
            "Errors",
            "Bad Long Status",
        )
        _log_event_helper(
            self.manager,
            self.manager.alan,
            "Invalid and also very long",
            "Errors",
            "Bad Long Status with Request",
            request=request,
        )

        # Long source
        _log_event_helper(
            self.manager,
            self.manager.alan,
            "Invalid",
            "Overly long source that will be too long",
            "Bad Status",
        )
        # None source
        _log_event_helper(
            self.manager, self.manager.alan, "Invalid", None, "Bad Status"
        )
        # Long sub-source
        _log_event_helper(
            self.manager,
            self.manager.alan,
            "Invalid",
            "Overly long source that will be too long",
            "Way too long sub source field",
        )
        # None sub-source
        _log_event_helper(
            self.manager,
            self.manager.alan,
            "Invalid",
            "Overly long source that will be too long",
            None,
        )

        # bad values - User
        _log_event_helper(
            self.manager,
            {"I am not a string": 0},
            "Invalid",
            "Errors",
            "Bad Status user str",
        )

        # user > 200
        _log_event_helper(
            self.manager,
            " If you're seeking inspiration for your next grand adventure, look no further that the Great White Continent and the Patagonian Fjords of Chile. Spend up to two weeks with no more than 149 other guests on these amazing trips - with a ratio of eight guests to a guide, the best in the industry, you'll have a quality experience on these small-scale-expedition trips. What's the big deal? Albatros Expeditions has slashed prices by more than half for two incredible cruise packages. Whether it's sailing down the Chilean coast or gliding past Antarctica's gigantic glaciers, Travelzoo members enjoy exclusive prices on these itineraries that get you up close to spectacular wildlife and astonishing scenery. In fact, this sale is even better than a 2-for-1 offer, our research puts the savings at up to 51%.",
            "Invalid",
            "Errors",
            "Bad Status user str",
        )

        # bad values - Request
        _log_event_helper(
            self.manager,
            {"I am not a string": 0},
            "Invalid Too",
            "Errors",
            "Bad Status user str",
            request={"I am not a string": 0},
        )
