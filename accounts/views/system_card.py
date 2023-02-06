from django.shortcuts import render


def system_card_view(request, system_card_id):
    """Show a system card"""

    return render(request, "accounts/system_card/system_card.html")
