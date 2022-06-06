from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
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


def _set_indicator_based_on_percentage(percentage):
    """set a value for indicator to be used as a class name in the template based upon the percentage"""

    # Set size of success circle
    indicator = ""
    if percentage > 20:
        indicator = "results-circle-quarter"
    if percentage >= 40:
        indicator = "results-circle-half"
    if percentage >= 60:
        indicator = "results-circle-three-quarter"
    if percentage >= 80:
        indicator = "results-circle-full"
    if percentage == 100:
        indicator = "results-circle-full-100"

    return indicator


def _percentage_from_match_points(ns_match_points, ew_match_points, ns_flag):
    """calculate the percentage using the matchpoints. Include the direction as well"""

    # Calculate percentage
    total_mps = ns_match_points + ew_match_points
    if ns_flag:
        percentage = ns_match_points / total_mps
    else:
        percentage = ew_match_points / total_mps

    return percentage * 100.0


@login_required()
def usebio_mp_pairs_results_summary_view(request, results_file_id):
    """Show the summary results for a usebio format event"""

    # TODO: Error checking, handle ties, one field or two
    # TODO: Masterpoints show type in title and change colours
    # TODO: Highlight team mates

    results_file = get_object_or_404(ResultsFile, pk=results_file_id)
    usebio = parse_usebio_file(results_file)["EVENT"]

    masterpoint_type = usebio.get("MASTER_POINT_TYPE", "No").title()

    if usebio["WINNER_TYPE"] == "2":
        # Two fields NS/EW
        return usebio_mp_pairs_results_summary_view_two_field(
            request, usebio, results_file, masterpoint_type
        )
    elif usebio["WINNER_TYPE"] == "1":
        return usebio_mp_pairs_results_summary_view_single_field(
            request, usebio, results_file, masterpoint_type
        )
    else:
        return HttpResponse(
            f"usebio winner type of {usebio['WINNER_TYPE']} not currently supported."
        )


def usebio_mp_pairs_results_summary_view_two_field(
    request, usebio, results_file, masterpoint_type
):
    """Handle two field NS/EW"""

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
        "results/usebio/usebio_results_summary_two_field_view.html",
        {
            "results_file": results_file,
            "usebio": usebio,
            "ns_scores": ns_scores,
            "ew_scores": ew_scores,
            "masterpoint_type": masterpoint_type,
        },
    )


def usebio_mp_pairs_results_summary_view_single_field(
    request, usebio, results_file, masterpoint_type
):
    """Handle single field e.g. Howell"""

    scores = []

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

        scores.append(row)

    # sort
    scores = sorted(scores, key=lambda d: d["position"])

    return render(
        request,
        "results/usebio/usebio_results_summary_single_field_view.html",
        {
            "results_file": results_file,
            "usebio": usebio,
            "scores": scores,
            "masterpoint_type": masterpoint_type,
        },
    )


@login_required()
def usebio_mp_pairs_details_view(request, results_file_id, pair_id):
    """Show the board by board results for a pair"""

    results_file = get_object_or_404(ResultsFile, pk=results_file_id)
    usebio = parse_usebio_file(results_file)["EVENT"]

    # Get position and percentage from usebio
    position = ""
    pair_percentage = ""

    for item in usebio["PARTICIPANTS"]["PAIR"]:
        pair = item["PAIR_NUMBER"]
        print(pair, pair_id)
        if pair == pair_id:
            position = int(item["PLACE"])
            pair_percentage = item["PERCENTAGE"]
            break

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

                percentage = _percentage_from_match_points(
                    ns_match_points, ew_match_points, ns_flag
                )

                indicator = _set_indicator_based_on_percentage(percentage)

                # change background colour so boards played against same opponents are grouped

                row = {
                    "board_number": board_number,
                    "contract": contract,
                    "played_by": played_by,
                    "lead": lead,
                    "tricks": tricks,
                    "indicator": indicator,
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
        "results/usebio/usebio_results_pairs_detail.html",
        {
            "usebio": usebio,
            "results_file": results_file,
            "pair_data": pair_data,
            "pair_id": pair_id,
            "pair_name": player_dict["names"][pair_id],
            "position": position,
            "pair_percentage": pair_percentage,
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
    ns_flag = True if pair_id == 0 else player_dict["direction"][pair_id] == "NS"
    board_data = get_traveller_info(
        usebio, board_number, player_dict, ns_flag, pair_id, request
    )

    # Now get hand record
    hand = {}
    double_dummy = None

    for board in usebio["HANDSET"]["BOARD"]:
        if int(board["BOARD_NUMBER"]) == board_number:
            for compass in board["HAND"]:
                hand[compass["DIRECTION"]] = {
                    "clubs": compass["CLUBS"],
                    "diamonds": compass["DIAMONDS"],
                    "hearts": compass["HEARTS"],
                    "spades": compass["SPADES"],
                }

            double_dummy = double_dummy_from_usebio(board["HAND"])

    if not double_dummy:
        return HttpResponse(f"Board {board_number} not found for this result")

    dealer, vulnerability = dealer_and_vulnerability_for_board(board_number)
    par_score, par_string = par_score_and_contract(double_dummy, vulnerability, dealer)

    # Add par score into the data
    row = {
        "score": par_score,
        "par_score": par_score,
        "par_string": par_string,
    }
    board_data.append(row)

    # Sort up or down depending on who is viewing it
    try:
        if ns_flag:
            board_data = sorted(board_data, key=lambda d: -d["score"])
        else:
            board_data = sorted(board_data, key=lambda d: d["score"])
    except TypeError:
        # score may be averaged or adjusted, not a number
        pass

    # Add High card points and losing trick count
    high_card_points, losing_trick_count = calculate_hcp_and_ltc(hand)

    previous_board = board_number - 1 if board_number > 1 else None

    total_boards = len(usebio["HANDSET"]["BOARD"])
    next_board = board_number + 1 if board_number < total_boards else None

    return render(
        request,
        "results/usebio/usebio_results_board_detail.html",
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
            "high_card_points": high_card_points,
            "losing_trick_count": losing_trick_count,
            "next_board": next_board,
            "previous_board": previous_board,
            "total_boards": total_boards,
            "total_boards_range": range(1, total_boards + 1),
        },
    )


def get_traveller_info(usebio, board_number, player_dict, ns_flag, pair_id, request):
    """extract traveller information about a board from a usebio record"""

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
                try:
                    score = int(score)
                except ValueError:
                    pass
                # TODO: Test and make more robust

                # Calculate percentage and score
                if type(score) is str:
                    # Score is adjusted
                    percentage = int(score[1:3])
                    score = 0
                else:
                    ew_match_points = float(traveller_line.get("EW_MATCH_POINTS"))
                    ns_match_points = float(traveller_line.get("NS_MATCH_POINTS"))
                    # Normal numeric score
                    percentage = _percentage_from_match_points(
                        ns_match_points, ew_match_points, ns_flag
                    )

                indicator = _set_indicator_based_on_percentage(percentage)

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
                    "score": score,
                    "percentage": percentage,
                    "ns_pair_number": ns_pair_number,
                    "ew_pair_number": ew_pair_number,
                    "ns_pair": ns_pair,
                    "ew_pair": ew_pair,
                    "tr_highlight": tr_highlight,
                    "indicator": indicator,
                }

                board_data.append(row)

    return board_data


def calculate_hcp_and_ltc(hand):
    """calculate the high card points and losing trick count for this board"""

    hcp = {}
    ltc = {}

    for compass in hand:
        hcp[compass] = 0
        ltc[compass] = 0
        for suit_name in hand[compass]:
            suit = hand[compass][suit_name]
            if suit:
                # HCP
                if suit.find("A") >= 0:
                    hcp[compass] += 4
                if suit.find("K") >= 0:
                    hcp[compass] += 3
                if suit.find("Q") >= 0:
                    hcp[compass] += 2
                if suit.find("J") >= 0:
                    hcp[compass] += 1
                # LTC
                if len(suit) == 1 and suit != "A":
                    ltc[compass] += 1
                elif len(suit) == 2:
                    if suit == "AK":
                        pass
                    elif suit[0] in ["A", "K"]:
                        ltc[compass] += 1
                    else:
                        ltc[compass] += 2
                elif suit[:3] == "AKQ":
                    pass
                elif suit[:2] in ["AK", "AQ", "KQ"]:
                    ltc[compass] += 1
                elif suit[0] in ["A", "K", "Q"]:
                    ltc[compass] += 2
                else:
                    ltc[compass] += 3

    return hcp, ltc
