from django.http import HttpResponse

from results.models import ResultsFile
from results.views.core import (
    double_dummy_from_usebio,
    score_for_contract,
    higher_than_other_suit,
    partner_for,
    lower_than_other_contract,
    next_contract_up,
    is_making_contract,
    opponent_for,
    opponents_list_for,
)
from results.views.usebio import parse_usebio_file


def temp(request):
    results_file = ResultsFile.objects.filter(pk=1).first()
    xml = parse_usebio_file(results_file)
    hand = xml["HANDSET"]["BOARD"][0]["HAND"]
    dd = double_dummy_from_usebio(hand)

    dd = {
        "N": {"S": 10, "H": 8, "D": 8, "C": 9, "NT": 6},
        "S": {"S": 6, "H": 5, "D": 6, "C": 4, "NT": 6},
        "E": {"S": 5, "H": 6, "D": 6, "C": 8, "NT": 6},
        "W": {"S": 6, "H": 9, "D": 6, "C": 9, "NT": 7},
    }

    resp = par_score_and_contract(dd, "Nil", "N")

    return HttpResponse(f"<lit>{resp}</lit>")


def _par_score_and_contract_best_contract_for_winner(
    dds_table, vulnerability, highest_bidder_player
):
    """sub to get the best contract for the auction winner or their partner.

    The highest contract is not necessarily the best scoring. e.g. 3NT+1 for 430 beats 5D= for 400

    """

    best_score = 0
    best_contract = None
    for suit in dds_table[highest_bidder_player]:
        tricks_available = dds_table[highest_bidder_player][suit]
        if tricks_available < 7:
            # Don't bother if not a valid contract
            continue
        contract = f"{tricks_available - 6}{suit}"
        # Get score
        score = score_for_contract(
            contract, vulnerability, highest_bidder_player, tricks_available
        )
        # Update best score if better
        # EW scores are best if smaller
        ns = highest_bidder_player in ["N", "S"]
        if ns and score > best_score or not ns and score < best_score:
            best_contract = contract
            best_score = score
    return best_score, best_contract


def _par_score_and_contract_auction_winner(dds_table, dealer):
    """sub to calculate the player who can bid the highest based on double dummy analysis"""

    highest_bidder_player = None
    highest_bidder_denomination = "C"
    highest_bidder_level = 0

    for compass in dds_table:
        for suit in dds_table[compass]:
            num = dds_table[compass][suit]

            # Check if this is the joint highest
            if num == highest_bidder_level and suit == highest_bidder_denomination:

                # closest to the dealer wins in a draw - they can bid it first
                order = "NESW"
                dealer_loc = order.find(dealer)

                # re-order the order with dealer first
                dealer_order = order[dealer_loc:] + order[:dealer_loc]

                existing_loc = dealer_order.find(highest_bidder_player)
                contender_loc = dealer_order.find(compass)

                if contender_loc < existing_loc:
                    # this one is earlier than the existing one, change
                    highest_bidder_level = num
                    highest_bidder_denomination = suit
                    highest_bidder_player = compass

                continue

            # See if this is the highest
            if num > highest_bidder_level or (
                num == highest_bidder_level
                and higher_than_other_suit(suit, highest_bidder_denomination)
            ):
                highest_bidder_level = num
                highest_bidder_denomination = suit
                highest_bidder_player = compass

    return highest_bidder_level, highest_bidder_denomination, highest_bidder_player


def _par_score_and_contract_final_check_equal_contracts_making(
    par_bidder, par_score, dds_table, vulnerability, equal_contracts
):
    """sub to find contracts with the same score"""

    direction = "NS" if par_bidder in ["N", "S"] else "EW"

    for suit in dds_table[par_bidder]:
        level = dds_table[par_bidder][suit] - 6
        if level < 1:
            continue
        contract = f"{level}{suit}"

        # check for same score
        if par_score == score_for_contract(
            contract, vulnerability, par_bidder, level + 6
        ):
            # Add to list, if already present then both can make it
            if contract in equal_contracts:
                equal_contracts[contract] = direction
            else:
                equal_contracts[contract] = par_bidder

    return equal_contracts


def _par_score_and_contract_final_check_equal_contracts_sacrifice(
    par_bidder, par_score, par_contract, dds_table, vulnerability, equal_contracts
):
    """sub to find contracts with the same score for sacrifices"""

    direction = "NS" if par_bidder in ["N", "S"] else "EW"

    level = int(par_contract[0])
    par_suit = par_contract[1]

    # for each suit look for a sacrifice at this level or higher. 4SX, need to check for 5CX not 4CX
    for suit in dds_table[par_bidder]:

        # How many tricks will we make in this suit
        tricks_taken = dds_table[par_bidder][suit]

        # Set level based on par score
        if higher_than_other_suit(suit, par_suit) or suit == par_suit:
            contract = f"{level}{suit}X"
        elif level < 7:
            contract = f"{level + 1}{suit}X"
        else:
            continue

        # check for same score
        if par_score == score_for_contract(
            contract, vulnerability, par_bidder, tricks_taken
        ):
            # Add to list, if already present then both can make it
            if contract in equal_contracts:
                equal_contracts[contract] = direction
            else:
                equal_contracts[contract] = par_bidder

    return equal_contracts


def _par_score_and_contract_final_check(
    dds_table, par_score, par_contract, par_bidder, vulnerability
):
    """finalise and return the parameters"""

    # Can partner make the same?

    # if par_contract is 3 chars long, this is doubled, so a sacrifice
    if len(par_contract) == 3:
        equal_contracts = _par_score_and_contract_final_check_equal_contracts_sacrifice(
            par_bidder, par_score, par_contract, dds_table, vulnerability, {}
        )
        equal_contracts = _par_score_and_contract_final_check_equal_contracts_sacrifice(
            partner_for(par_bidder),
            par_score,
            par_contract,
            dds_table,
            vulnerability,
            equal_contracts,
        )
    else:
        # Making. Get all contracts for this score, this player and their partner
        equal_contracts = _par_score_and_contract_final_check_equal_contracts_making(
            par_bidder, par_score, dds_table, vulnerability, {}
        )
        equal_contracts = _par_score_and_contract_final_check_equal_contracts_making(
            partner_for(par_bidder),
            par_score,
            dds_table,
            vulnerability,
            equal_contracts,
        )

    # Build par_string for making contract
    par_string = "".join(
        f" {contract} by {equal_contracts[contract]} or" for contract in equal_contracts
    )

    par_string = par_string[1:-3]  # remove last "or" and first space
    par_string += f" for {par_score}"

    return par_score, par_string


def _par_score_and_contract_look_for_better_sacrifice(
    current_bid, dds_table, vulnerability, current_bidders, par_score, sign
):
    """Once we find a working sacrifice against a contract, this will look for a better one.
    Without this, we could lock in a bad sacrifice and not have the opposition bid on.
    """

    par_bid = current_bid

    while lower_than_other_contract(current_bid, "7N"):
        current_bid = next_contract_up(current_bid)
        suit = current_bid[1]
        this_player_score = score_for_contract(
            f"{current_bid}X",
            vulnerability,
            current_bidders[0],
            dds_table[current_bidders[0]][suit],
        )
        this_player_partner_score = score_for_contract(
            f"{current_bid}X",
            vulnerability,
            current_bidders[1],
            dds_table[current_bidders[1]][suit],
        )
        if sign:  # NS
            this_score = max(this_player_score, this_player_partner_score)
        else:  # EW
            this_score = min(this_player_score, this_player_partner_score)

        if sign and this_score > par_score or not sign and this_score < par_score:
            # better score
            par_score = this_score
            par_bid = current_bid

    return par_bid, par_score


def _par_score_and_contract_run_through_auction(
    best_contract, highest_bidder_player, best_score, dds_table, vulnerability
):
    """sub to run through the rest of the auction from the best score for the winning side and
    see what happens"""

    # set up starting point

    # latest bid
    current_bid = best_contract

    # which side
    current_bidders = opponents_list_for(highest_bidder_player)

    # current par values
    par_contract = current_bid
    par_bidder = highest_bidder_player
    par_score = best_score

    # run through the auction up to 7NT
    while lower_than_other_contract(current_bid, "7N"):
        current_bid = next_contract_up(current_bid)
        # Scores are always with reference to NS, need to see if we are EW
        #  High scores good NS, bad EW, low or negative scores good EW, bad NS
        sign = current_bidders[0] in ["N", "S"]

        # making contracts take over
        making_by_first_player = is_making_contract(
            dds_table, current_bid, current_bidders[0]
        )
        making_by_second_player = is_making_contract(
            dds_table, current_bid, current_bidders[1]
        )

        if making_by_first_player or making_by_second_player:
            par_contract = current_bid
            if making_by_first_player:
                par_bidder = current_bidders[0]
            else:
                par_bidder = current_bidders[1]
            par_score = score_for_contract(
                current_bid,
                vulnerability,
                par_bidder,
                dds_table[par_bidder][current_bid[1]],
            )
            # swap to other side to bid
            current_bidders = opponents_list_for(current_bidders[0])

        # handle sacrifices, could be a better score. Check for player and partner
        else:
            suit = current_bid[1]
            this_player_score = score_for_contract(
                f"{current_bid}X",
                vulnerability,
                current_bidders[0],
                dds_table[current_bidders[0]][suit],
            )
            this_player_partner_score = score_for_contract(
                f"{current_bid}X",
                vulnerability,
                current_bidders[1],
                dds_table[current_bidders[1]][suit],
            )

            if sign:  # NS
                this_score = max(this_player_score, this_player_partner_score)
            else:  # EW
                this_score = min(this_player_score, this_player_partner_score)

            if sign and this_score > par_score or not sign and this_score < par_score:
                # We have found a working sacrifice, but we might have an even better one
                # before we lock this in, look higher. This may bump up the current bid and change
                # this_score
                (
                    current_bid,
                    this_score,
                ) = _par_score_and_contract_look_for_better_sacrifice(
                    current_bid,
                    dds_table,
                    vulnerability,
                    current_bidders,
                    this_score,
                    sign,
                )

                par_contract = f"{current_bid}X"
                par_bidder = current_bidders[0]
                par_score = this_score
                current_bidders = opponents_list_for(current_bidders[0])

    # TODO: Handle special case of sacrificing in opponents contract

    # Auction is over, return pars
    return par_score, par_contract, par_bidder


def par_score_and_contract(dds_table, vulnerability, dealer):
    """Calculate the par score for a hand. Par score is the best score for both sides if they bid to the
    perfect double dummy contract. Sacrifices are always doubled.

    https://bridgecomposer.com/Par.htm

    args:
        dds_table(str): output from double_dummy_from_usebio()
        vulnerability(str): for this board NS/EW/All/Nil
        dealer(str): N/S/E/W
    """

    # dds_table is like: 'N': {'S': 6, 'H': 6, 'D': 6, 'C': 4, 'NT': 6}, 'S': {'S'
    # North Spades Tricks Hearts Tricks etc

    # Quick fix on the DDS Table
    # - change "NT" to "N". We don't do this in the loader as we want NT for the display
    for compass in dds_table:
        dds_table[compass]["N"] = dds_table[compass]["NT"]
        del dds_table[compass]["NT"]

    # calculate who wins the auction, the highest bid
    (
        highest_bidder_level,
        highest_bidder_denomination,
        highest_bidder_player,
    ) = _par_score_and_contract_auction_winner(dds_table, dealer)

    # Now get the best scoring contract for this side
    best_score, best_contract = _par_score_and_contract_best_contract_for_winner(
        dds_table, vulnerability, highest_bidder_player
    )
    (
        partner_best_score,
        partner_best_contract,
    ) = _par_score_and_contract_best_contract_for_winner(
        dds_table, vulnerability, partner_for(highest_bidder_player)
    )

    ns = highest_bidder_player in ["N", "S"]
    if (
        ns
        and partner_best_score > best_score
        or not ns
        and partner_best_score < best_score
    ):
        best_score = partner_best_score
        best_contract = partner_best_contract

    # Now see if the opponents can do anything better
    par_score, par_contract, par_bidder = _par_score_and_contract_run_through_auction(
        best_contract, highest_bidder_player, best_score, dds_table, vulnerability
    )

    # finally, it is possible that their partner could make the same contract or another contract makes the same
    return _par_score_and_contract_final_check(
        dds_table, par_score, par_contract, par_bidder, vulnerability
    )
