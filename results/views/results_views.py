from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from results.models import ResultsFile
from results.views.core import (
    double_dummy_from_usebio,
    dealer_and_vulnerability_for_board,
)
from results.views.par_contract import par_score_and_contract
from results.views.usebio import parse_usebio_file


def _get_player_names_by_id(usebio):
    """Helper to get the player names, numbers and directions"""

    player_dict = {"system_numbers": {}, "names": {}, "direction": {}}
    for item in usebio["PARTICIPANTS"]["PAIR"]:

        # Names
        player_1 = item["PLAYER"][0]["PLAYER_NAME"].title()
        player_2 = item["PLAYER"][1]["PLAYER_NAME"].title()
        this_pair_id = item["PAIR_NUMBER"]
        players_names = _format_pair_name(player_1, player_2)
        player_dict["names"][this_pair_id] = players_names

        # system numbers
        try:
            player_1_system_number = int(item["PLAYER"][0]["NATIONAL_ID_NUMBER"])
            player_2_system_number = int(item["PLAYER"][1]["NATIONAL_ID_NUMBER"])
        except TypeError:
            player_1_system_number = None
            player_2_system_number = None

        player_dict["system_numbers"][this_pair_id] = [
            player_1_system_number,
            player_2_system_number,
        ]

        # Direction
        player_dict["direction"][this_pair_id] = item.get("DIRECTION")

    return player_dict


def _format_pair_name(player_1, player_2):
    """helper function to nicely format a pair name"""

    players_names = f"{player_1} & {player_2}"

    # for couple show name as Mary & David Smith
    surname1 = player_1.split(" ")[-1]
    surname2 = player_2.split(" ")[-1]
    if surname1 == surname2:
        first_name1 = player_1.split(" ")[0]
        players_names = f"{first_name1} & {player_2}"

    return players_names


@login_required()
def usebio_mp_pairs_results_summary_view(request, results_file_id):
    """Show the summary results for a usebio format event"""

    # TODO: Error checking, handle ties, one field or two
    # TODO: Link to user and highlight name
    # TODO: Masterpoints show type in title and change colours
    # TODO: Highlight team mates

    results_file = get_object_or_404(ResultsFile, pk=results_file_id)
    usebio = parse_usebio_file(results_file)["EVENT"]

    masterpoint_type = usebio["MASTER_POINT_TYPE"].title()

    if usebio["WINNER_TYPE"] == "2":
        # Two fields NS/EW

        ns_scores = []
        ew_scores = []

        for item in usebio["PARTICIPANTS"]["PAIR"]:
            player_1 = item["PLAYER"][0]["PLAYER_NAME"].title()
            player_2 = item["PLAYER"][1]["PLAYER_NAME"].title()
            try:
                player_1_system_number = int(item["PLAYER"][0]["NATIONAL_ID_NUMBER"])
                player_2_system_number = int(item["PLAYER"][1]["NATIONAL_ID_NUMBER"])
            except TypeError:
                player_1_system_number = None
                player_2_system_number = None

            # This may break for ties
            position = int(item["PLACE"])
            masterpoints = int(item["MASTER_POINTS_AWARDED"]) / 100.0
            pair_number = item["PAIR_NUMBER"]
            direction = item["DIRECTION"]
            percentage = item["PERCENTAGE"]

            players_names = _format_pair_name(player_1, player_2)

            # See if this user is in the data and highlight
            if request.user.system_number in [
                player_1_system_number,
                player_2_system_number,
            ]:
                tr_highlight = "bg-warning"
            else:
                tr_highlight = ""

            row = {
                "player_1": player_1,
                "player_2": player_2,
                "players_names": players_names,
                "player_1_system_number": player_1_system_number,
                "player_2_system_number": player_2_system_number,
                "position": position,
                "masterpoints": masterpoints,
                "pair_number": pair_number,
                "percentage": percentage,
                "tr_highlight": tr_highlight,
            }

            if direction == "NS":
                ns_scores.append(row)
            else:
                ew_scores.append(row)

        # sort
        ns_scores = sorted(ns_scores, key=lambda d: d["position"])
        ew_scores = sorted(ew_scores, key=lambda d: d["position"])

        return render(
            request,
            "results/usebio_results_summary_two_field_view.html",
            {
                "results_file": results_file,
                "usebio": usebio,
                "ns_scores": ns_scores,
                "ew_scores": ew_scores,
                "masterpoint_type": masterpoint_type,
            },
        )


@login_required()
def usebio_mp_pairs_details_view(request, results_file_id, pair_id):
    """Show the board by board results for a pair"""

    results_file = get_object_or_404(ResultsFile, pk=results_file_id)
    usebio = parse_usebio_file(results_file)["EVENT"]

    # First get all the players names and details
    player_dict = _get_player_names_by_id(usebio)

    pair_data = []

    for board in usebio["BOARD"]:
        board_number = int(board.get("BOARD_NUMBER"))
        for traveller_line in board.get("TRAVELLER_LINE"):
            ns_pair = traveller_line.get("NS_PAIR_NUMBER")
            ew_pair = traveller_line.get("EW_PAIR_NUMBER")
            if pair_id in [ns_pair, ew_pair]:
                # Our pair played this board and this is the score
                if pair_id == ns_pair:
                    opponents = player_dict["names"].get(ew_pair)
                    opponents_pair_id = ew_pair
                    ns_flag = True
                else:
                    opponents = player_dict["names"].get(ns_pair)
                    opponents_pair_id = ns_pair
                    ns_flag = False
                contract = traveller_line.get("CONTRACT")
                played_by = traveller_line.get("PLAYED_BY")
                lead = traveller_line.get("LEAD")
                tricks = traveller_line.get("TRICKS")
                score = traveller_line.get("SCORE")
                ns_match_points = float(traveller_line.get("NS_MATCH_POINTS"))
                ew_match_points = float(traveller_line.get("EW_MATCH_POINTS"))

                # Calculate percentage
                total_mps = ns_match_points + ew_match_points
                if ns_flag:
                    percentage = ns_match_points / total_mps
                else:
                    percentage = ew_match_points / total_mps

                percentage = percentage * 100.0

                row = {
                    "board_number": board_number,
                    "contract": contract,
                    "played_by": played_by,
                    "lead": lead,
                    "tricks": tricks,
                    "score": score,
                    "opponents": opponents,
                    "opponents_pair_id": opponents_pair_id,
                    "percentage": percentage,
                }

                pair_data.append(row)

        # sort
        pair_data = sorted(pair_data, key=lambda d: d["board_number"])

    return render(
        request,
        "results/usebio_results_pairs_detail.html",
        {
            "usebio": usebio,
            "results_file": results_file,
            "pair_data": pair_data,
            "pair_id": pair_id,
            "pair_name": player_dict["names"][pair_id],
        },
    )


@login_required()
def usebio_mp_pairs_board_view(request, results_file_id, board_number, pair_id):
    """Show the traveller for a board. If pair_id is provided then we show it from the
    perspective of that pair"""

    results_file = get_object_or_404(ResultsFile, pk=results_file_id)
    usebio = parse_usebio_file(results_file)

    # First get all the players names and numbers
    player_dict = _get_player_names_by_id(usebio["EVENT"])

    # If we got a pair_number, then see which way they were sitting on this board, default view to NS
    if pair_id == 0:
        ns_flag = True
    else:
        if player_dict["direction"][pair_id] == "NS":
            ns_flag = True
        else:
            ns_flag = False

    board_data = []

    for board in usebio["EVENT"]["BOARD"]:
        this_board_number = int(board.get("BOARD_NUMBER"))
        if this_board_number == board_number:
            # Found our board - go through the traveller lines
            for traveller_line in board.get("TRAVELLER_LINE"):
                ns_pair_number = traveller_line.get("NS_PAIR_NUMBER")
                ns_pair = player_dict["names"].get(ns_pair_number)
                ew_pair_number = traveller_line.get("EW_PAIR_NUMBER")
                ew_pair = player_dict["names"].get(ew_pair_number)
                contract = traveller_line.get("CONTRACT")
                played_by = traveller_line.get("PLAYED_BY")
                lead = traveller_line.get("LEAD")
                tricks = traveller_line.get("TRICKS")
                score = traveller_line.get("SCORE")
                ns_match_points = float(traveller_line.get("NS_MATCH_POINTS"))
                ew_match_points = float(traveller_line.get("EW_MATCH_POINTS"))

                # Calculate percentage
                total_mps = ns_match_points + ew_match_points
                if ns_flag:
                    percentage = ns_match_points / total_mps
                else:
                    percentage = ew_match_points / total_mps

                percentage = percentage * 100.0

                # highlight row of interest
                if pair_id in [ns_pair_number, ew_pair_number]:
                    if (
                        request.user.system_number
                        in player_dict["system_numbers"][pair_id]
                    ):
                        # This user
                        tr_highlight = "bg-warning"
                    else:
                        # Another user
                        tr_highlight = "bg-info"
                else:
                    tr_highlight = ""

                row = {
                    "board_number": board_number,
                    "contract": contract,
                    "played_by": played_by,
                    "lead": lead,
                    "tricks": tricks,
                    "score": int(score),
                    "percentage": percentage,
                    "ns_pair": ns_pair,
                    "ew_pair": ew_pair,
                    "tr_highlight": tr_highlight,
                }

                board_data.append(row)

    # Now get hand record
    hand = {}
    for board in usebio["HANDSET"]["BOARD"]:
        if int(board["BOARD_NUMBER"]) == board_number:
            for compass in board["HAND"]:
                hand[compass["DIRECTION"]] = {}
                hand[compass["DIRECTION"]]["clubs"] = compass["CLUBS"]
                hand[compass["DIRECTION"]]["diamonds"] = compass["DIAMONDS"]
                hand[compass["DIRECTION"]]["hearts"] = compass["HEARTS"]
                hand[compass["DIRECTION"]]["spades"] = compass["SPADES"]

            double_dummy = double_dummy_from_usebio(board["HAND"])

    dealer, vulnerability = dealer_and_vulnerability_for_board(board_number)
    par_score, par_string = par_score_and_contract(double_dummy, vulnerability, dealer)

    # Add par score into the data
    row = {
        "score": par_score,
        "par_score": par_score,
        "par_string": par_string,
    }
    board_data.append(row)

    # sort
    if ns_flag:
        board_data = sorted(board_data, key=lambda d: -d["score"])
    else:
        board_data = sorted(board_data, key=lambda d: d["score"])

    return render(
        request,
        "results/usebio_results_board_detail.html",
        {
            "usebio": usebio.get("EVENT"),
            "results_file": results_file,
            "board_data": board_data,
            "board_number": board_number,
            "pair_id": pair_id,
            "hand": hand,
            "double_dummy": double_dummy,
            "dealer": dealer,
            "vulnerability": vulnerability,
            "par_score": par_score,
            "par_string": par_string,
        },
    )
