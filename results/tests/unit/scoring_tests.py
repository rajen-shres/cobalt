from results.views.core import score_for_contract
from tests.test_manager import CobaltTestManagerIntegration


class ScoringTests:
    """Unit tests for scoring"""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager

    def scoring_tests(self):
        """Tests for the scoring function"""

        test_data = [
            # part scores making
            ("1C", "All", "N", 7, 70),
            ("1H", "Nil", "E", 9, -140),
            ("1S", "EW", "W", 5, 200),
            # part scores failing
            ("1N", "Nil", "N", 6, -50),
            ("4C", "NS", "S", 7, -300),
            ("3H", "EW", "S", 8, -50),
            # Game making
            ("4S", "EW", "S", 11, 450),
            ("3N", "All", "S", 10, 630),
            ("5D", "EW", "W", 11, -600),
            # Game failing
            ("4S", "EW", "S", 8, -100),
            ("3N", "All", "W", 7, 200),
            ("5D", "EW", "W", 10, 100),
            # small slam making
            ("6S", "Nil", "S", 12, 980),
            ("6N", "All", "S", 13, 1470),
            ("6D", "EW", "W", 12, -1370),
            # small slam failing
            ("6S", "Nil", "S", 10, -100),
            ("6N", "All", "S", 11, -100),
            ("6D", "EW", "W", 10, 200),
            # grand slam making
            ("7S", "Nil", "S", 13, 1510),
            ("7N", "All", "N", 13, 2220),
            ("7D", "EW", "W", 13, -2140),
            # grand slam failing
            ("7S", "Nil", "S", 12, -50),
            ("7N", "All", "N", 6, -700),
            ("7D", "EW", "W", 11, 200),
            # doubled failing
            ("3HX", "EW", "S", 6, -500),
            ("7NX", "EW", "E", 8, 1400),
            ("3NX", "Nil", "E", 5, 800),
            # doubled part scores making
            ("1SX", "EW", "N", 7, 160),
            ("1SX", "EW", "N", 9, 360),
            ("2NX", "All", "W", 9, -890),
            ("3DX", "Nil", "S", 9, 470),
            ("3DX", "Nil", "S", 10, 570),
            ("3DX", "Nil", "S", 11, 670),
            ("3DX", "Nil", "S", 12, 770),
            ("3DX", "Nil", "S", 12, 770),
            # redoubled part scores making
            ("3DXX", "Nil", "S", 9, 640),
            ("3DXX", "Nil", "S", 11, 1040),
            ("3DXX", "NS", "S", 11, 1640),
            ("3HXX", "NS", "S", 10, 1360),
            # Doubled games making
            ("3NX", "Nil", "W", 10, -650),
            ("3NX", "EW", "W", 12, -1350),
        ]

        failing = []

        for this_test in test_data:
            contract, vul, declarer, made, score = this_test

            result = score_for_contract(contract, vul, declarer, made)

            if result != score:
                failing.append((this_test, result))

        self.manager.save_results(
            status=not failing,
            test_name="Score testing",
            test_description="Tests for score_for_contract. We don't test everything, there are too many combinations.",
            output=f"These tests failed: {failing}",
        )
