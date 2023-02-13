from django.shortcuts import render


def system_card_view(request, system_card_id):
    """Show a system card"""

    all_responses = {}
    all_responses["LINK-1C"] = {
        1: {
            "1D": "6+ HCP 4+!Ds",
            "1H": "6+ HCP 4+!Hs or some other thing that comes up",
            "1S": "6+ HCP 4+!Ss",
            "1N": "6-9 HCP",
        },
        2: {
            "2C": "10+ HCP 4+!Cs",
            "2D": "10+ HCP 4+!Cs",
            "2H": "10+ HCP 4+!Cs",
            "2S": "10+ HCP 4+!Cs",
            "2N": "6-9 HCP",
        },
        3: {
            "3C": "10+ HCP 4+!Cs",
            "3D": "10+ HCP 4+!Cs",
            "3H": "10+ HCP 4+!Cs",
            "3S": "10+ HCP 4+!Cs",
            "3N": "6-9 HCP",
        },
        4: {
            "4C": "10+ HCP 4+!Cs",
            "4D": "10+ HCP 4+!Cs",
        },
    }
    all_responses["LINK-1D"] = {
        1: {
            "1H": "6+ HCP 4+!Hs or some other thing that comes up",
            "1S": "You clicked 1!D",
            "1N": "6-9 HCP",
        },
        2: {
            "2C": "10+ HCP 4+!Cs",
            "2D": "10+ HCP 4+!Cs",
            "2H": "10+ HCP 4+!Cs",
            "2S": "10+ HCP 4+!Cs",
            "2N": "6-9 HCP",
        },
        3: {
            "3C": "10+ HCP 4+!Cs",
            "3D": "10+ HCP 4+!Cs",
            "3H": "10+ HCP 4+!Cs",
            "3S": "10+ HCP 4+!Cs",
            "3N": "6-9 HCP",
        },
        4: {
            "4C": "10+ HCP 4+!Cs",
            "4D": "10+ HCP 4+!Cs",
        },
    }
    all_responses["LINK-1H"] = {
        1: {
            "1S": "You clicked 1!D",
            "1N": "6-9 HCP",
        },
        2: {
            "2C": "10+ HCP 4+!Cs",
            "2D": "10+ HCP 4+!Cs",
            "2H": "10+ HCP 4+!Cs",
            "2S": "10+ HCP 4+!Cs",
            "2N": "6-9 HCP",
        },
        3: {
            "3C": "10+ HCP 4+!Cs",
            "3D": "10+ HCP 4+!Cs",
            "3H": "10+ HCP 4+!Cs",
            "3S": "10+ HCP 4+!Cs",
            "3N": "6-9 HCP",
        },
        4: {
            "4C": "10+ HCP 4+!Cs",
            "4D": "10+ HCP 4+!Cs",
        },
    }

    all_responses["LINK-1S"] = {
        1: {
            "1N": "6-9 HCP",
        },
        2: {
            "2C": "10+ HCP 4+!Cs",
            "2D": "10+ HCP 4+!Cs",
            "2H": "10+ HCP 4+!Cs",
            "2S": "10+ HCP 4+!Cs",
            "2N": "6-9 HCP",
        },
        3: {
            "3C": "10+ HCP 4+!Cs",
            "3D": "10+ HCP 4+!Cs",
            "3H": "10+ HCP 4+!Cs",
            "3S": "10+ HCP 4+!Cs",
            "3N": "6-9 HCP",
        },
        4: {
            "4C": "10+ HCP 4+!Cs",
            "4D": "10+ HCP 4+!Cs",
        },
    }

    all_responses["LINK-1N"] = {
        2: {
            "2C": "10+ HCP 4+!Cs",
            "2D": "10+ HCP 4+!Cs",
            "2H": "10+ HCP 4+!Cs",
            "2S": "10+ HCP 4+!Cs",
            "2N": "6-9 HCP",
        },
        3: {
            "3C": "10+ HCP 4+!Cs",
            "3D": "10+ HCP 4+!Cs",
            "3H": "10+ HCP 4+!Cs",
            "3S": "10+ HCP 4+!Cs",
            "3N": "6-9 HCP",
        },
        4: {
            "4C": "10+ HCP 4+!Cs",
            "4D": "10+ HCP 4+!Cs",
        },
    }

    all_responses["LINK-2C"] = {
        2: {
            "2D": "10+ HCP 4+!Cs",
            "2H": "10+ HCP 4+!Cs",
            "2S": "10+ HCP 4+!Cs",
            "2N": "6-9 HCP",
        },
        3: {
            "3C": "10+ HCP 4+!Cs",
            "3D": "10+ HCP 4+!Cs",
            "3H": "10+ HCP 4+!Cs",
            "3S": "10+ HCP 4+!Cs",
            "3N": "6-9 HCP",
        },
        4: {
            "4C": "10+ HCP 4+!Cs",
            "4D": "10+ HCP 4+!Cs",
        },
    }

    all_responses["LINK-2D"] = {
        2: {
            "2H": "10+ HCP 4+!Cs",
            "2S": "10+ HCP 4+!Cs",
            "2N": "6-9 HCP",
        },
        3: {
            "3C": "10+ HCP 4+!Cs",
            "3D": "10+ HCP 4+!Cs",
            "3H": "10+ HCP 4+!Cs",
            "3S": "10+ HCP 4+!Cs",
            "3N": "6-9 HCP",
        },
        4: {
            "4C": "10+ HCP 4+!Cs",
            "4D": "10+ HCP 4+!Cs",
        },
    }

    all_responses["LINK-2H"] = {
        2: {
            "2S": "10+ HCP 4+!Cs",
            "2N": "6-9 HCP",
        },
        3: {
            "3C": "10+ HCP 4+!Cs",
            "3D": "10+ HCP 4+!Cs",
            "3H": "10+ HCP 4+!Cs",
            "3S": "10+ HCP 4+!Cs",
            "3N": "6-9 HCP",
        },
        4: {
            "4C": "10+ HCP 4+!Cs",
            "4D": "10+ HCP 4+!Cs",
        },
    }

    all_responses["LINK-2S"] = {
        2: {
            "2N": "6-9 HCP",
        },
        3: {
            "3C": "10+ HCP 4+!Cs",
            "3D": "10+ HCP 4+!Cs",
            "3H": "10+ HCP 4+!Cs",
            "3S": "10+ HCP 4+!Cs",
            "3N": "6-9 HCP",
        },
        4: {
            "4C": "10+ HCP 4+!Cs",
            "4D": "10+ HCP 4+!Cs",
        },
    }

    all_responses["LINK-2N"] = {
        3: {
            "3C": "10+ HCP 4+!Cs",
            "3D": "10+ HCP 4+!Cs",
            "3H": "10+ HCP 4+!Cs",
            "3S": "10+ HCP 4+!Cs",
            "3N": "6-9 HCP",
        },
        4: {
            "4C": "10+ HCP 4+!Cs",
            "4D": "10+ HCP 4+!Cs",
        },
    }

    return render(
        request,
        "accounts/system_card/system_card.html",
        {"all_responses": all_responses},
    )
