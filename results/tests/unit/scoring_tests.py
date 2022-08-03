from results.views.core import score_for_contract
from results.views.par_contract import par_score_and_contract
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

    def par_score_tests(self):
        """Tests for the par score function"""

        passing = True
        failing = []

        #####################################
        test_number = 1

        # Both 3NT and 5C make. 3NT better. No sacrifice.
        dds_table = {
            "N": {"S": 8, "H": 8, "D": 8, "C": 11, "NT": 10},
            "S": {"S": 6, "H": 5, "D": 6, "C": 4, "NT": 6},
            "E": {"S": 5, "H": 6, "D": 6, "C": 8, "NT": 6},
            "W": {"S": 6, "H": 7, "D": 6, "C": 8, "NT": 7},
        }

        par_score, par_string = par_score_and_contract(dds_table, "Nil", "N")
        if par_score != 430:
            passing = False
            failing.append(test_number)
            print(test_number, par_score, par_string)

        #####################################
        test_number = 2

        # NS can bid to 5Cs but EW sacrifice in 5Hs
        dds_table = {
            "N": {"S": 9, "H": 8, "D": 8, "C": 11, "NT": 9},
            "S": {"S": 6, "H": 5, "D": 6, "C": 4, "NT": 6},
            "E": {"S": 5, "H": 10, "D": 6, "C": 8, "NT": 6},
            "W": {"S": 6, "H": 10, "D": 6, "C": 8, "NT": 7},
        }

        par_score, par_string = par_score_and_contract(dds_table, "Nil", "N")
        if par_score != 100:
            passing = False
            failing.append(test_number)
            print(test_number, par_score, par_string)

        #####################################
        test_number = 3

        # 1NT makes both ways. N is dealer so wins contract.
        dds_table = {
            "N": {"S": 5, "H": 5, "D": 5, "C": 6, "NT": 7},
            "S": {"S": 5, "H": 5, "D": 6, "C": 4, "NT": 6},
            "E": {"S": 5, "H": 5, "D": 6, "C": 6, "NT": 6},
            "W": {"S": 6, "H": 5, "D": 6, "C": 7, "NT": 7},
        }

        par_score, par_string = par_score_and_contract(dds_table, "Nil", "N")
        if par_score != 90:
            passing = False
            failing.append(test_number)
            print(test_number, par_score, par_string)

        ####################################
        test_number = 4

        # Doubled part score is best
        dds_table = {
            "N": {"S": 9, "H": 8, "D": 8, "C": 9, "NT": 6},
            "S": {"S": 6, "H": 5, "D": 6, "C": 4, "NT": 6},
            "E": {"S": 5, "H": 1, "D": 6, "C": 8, "NT": 6},
            "W": {"S": 6, "H": 7, "D": 6, "C": 9, "NT": 7},
        }

        par_score, par_string = par_score_and_contract(dds_table, "Nil", "N")
        if par_score != 100:
            passing = False
            failing.append(test_number)
            print(test_number, par_score, par_string)

        ####################################
        test_number = 5

        # Check for one sacrificer making and not the other
        dds_table = {
            "N": {"S": 9, "H": 8, "D": 8, "C": 11, "NT": 9},
            "S": {"S": 6, "H": 5, "D": 6, "C": 4, "NT": 6},
            "E": {"S": 5, "H": 10, "D": 6, "C": 8, "NT": 6},
            "W": {"S": 6, "H": 1, "D": 6, "C": 8, "NT": 7},
        }

        par_score, par_string = par_score_and_contract(dds_table, "Nil", "N")
        if par_score != 100:
            passing = False
            failing.append(test_number)
            print(test_number, par_score, par_string)

        ####################################
        test_number = 6

        # EW contracts
        dds_table = {
            "N": {"S": 8, "H": 8, "D": 8, "C": 7, "NT": 9},
            "S": {"S": 6, "H": 5, "D": 6, "C": 4, "NT": 6},
            "E": {"S": 5, "H": 10, "D": 6, "C": 8, "NT": 6},
            "W": {"S": 6, "H": 1, "D": 6, "C": 8, "NT": 7},
        }

        par_score, par_string = par_score_and_contract(dds_table, "Nil", "S")
        if par_score != -100:
            passing = False
            failing.append(test_number)
            print(test_number, par_score, par_string)

        #####################################
        test_number = 7

        # EW contracts
        dds_table = {
            "N": {"S": 7, "H": 7, "D": 7, "C": 7, "NT": 6},
            "S": {"S": 6, "H": 5, "D": 6, "C": 4, "NT": 6},
            "E": {"S": 5, "H": 10, "D": 6, "C": 8, "NT": 6},
            "W": {"S": 10, "H": 1, "D": 6, "C": 8, "NT": 7},
        }

        par_score, par_string = par_score_and_contract(dds_table, "EW", "S")
        if par_score != -620:
            passing = False
            failing.append(test_number)
            print(test_number, par_score, par_string)

        #####################################
        test_number = 8

        # EW contracts NS sacrifice
        dds_table = {
            "N": {"S": 9, "H": 8, "D": 8, "C": 7, "NT": 9},
            "S": {"S": 6, "H": 5, "D": 6, "C": 4, "NT": 6},
            "E": {"S": 5, "H": 10, "D": 6, "C": 8, "NT": 6},
            "W": {"S": 6, "H": 1, "D": 6, "C": 8, "NT": 7},
        }

        par_score, par_string = par_score_and_contract(dds_table, "All", "S")
        if par_score != -200:
            passing = False
            failing.append(test_number)
            print(test_number, par_score, par_string)

        #####################################
        test_number = 9

        # both making same contract - dealer dictates winner. South can't make 1N so E wins.
        dds_table = {
            "N": {"S": 5, "H": 5, "D": 5, "C": 5, "NT": 7},
            "S": {"S": 6, "H": 5, "D": 6, "C": 4, "NT": 6},
            "E": {"S": 5, "H": 5, "D": 6, "C": 5, "NT": 7},
            "W": {"S": 6, "H": 1, "D": 6, "C": 5, "NT": 7},
        }

        par_score, par_string = par_score_and_contract(dds_table, "All", "S")
        if par_score != -90:
            passing = False
            failing.append(test_number)
            print(test_number, par_score, par_string)

        #####################################
        test_number = 10

        # Real world problem board
        dds_table = {
            "N": {"S": 9, "H": 2, "D": 5, "C": 2, "NT": 5},
            "S": {"S": 9, "H": 2, "D": 5, "C": 2, "NT": 5},
            "E": {"S": 4, "H": 10, "D": 8, "C": 11, "NT": 5},
            "W": {"S": 4, "H": 10, "D": 8, "C": 11, "NT": 5},
        }

        par_score, par_string = par_score_and_contract(dds_table, "Nil", "N")
        if par_score != -100:
            passing = False
            failing.append(test_number)
            print(test_number, par_score, par_string)

        # Results

        self.manager.save_results(
            status=passing,
            test_name="Par contract and score testing",
            test_description="Tests for par score.",
            output=f"These tests failed (see numbers in code): {failing}",
        )
