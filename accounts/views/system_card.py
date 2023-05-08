import io
import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, FileResponse, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from accounts.forms import SystemCardForm
from accounts.models import SystemCard, User


def _save_card_as_template(system_card, filename):
    """Utility to save a card as a template"""

    with open(f"accounts/system_card_templates/{filename}", "w") as outfile:

        # Grab values for system_card
        for name in dir(system_card):
            if name[0] != "_":
                try:
                    val = getattr(system_card, name)
                    if type(val) in [str, int, bool, User]:
                        outfile.write(f"{name}:{val}\n")
                except AttributeError:
                    pass


def system_card_view(request, user_id, system_card_name):
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

    user = User.objects.filter(pk=user_id).first()
    if not user:
        raise Http404

    system_card = (
        SystemCard.objects.filter(user=user, card_name=system_card_name)
        .order_by("-save_date")
        .first()
    )

    if not system_card:
        raise Http404

    form = SystemCardForm(instance=system_card)

    return render(
        request,
        "accounts/system_card/system_card.html",
        {
            "all_responses": all_responses,
            "form": form,
            "system_card": system_card,
            "editable": False,
            "template": "empty.html",
        },
    )


@login_required
def system_card_edit(request, system_card_name):
    """Edit a system card"""

    system_card = (
        SystemCard.objects.filter(user=request.user, card_name=system_card_name)
        .order_by("-save_date")
        .first()
    )
    if not system_card:
        if not request.POST:
            raise Http404
        else:
            return HttpResponse("Card not found")

    if system_card.user != request.user:
        return HttpResponse("Access Denied. You are not the owner of this system card.")

    if request.method == "POST":
        form = SystemCardForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                "accounts/system_card/system_card_save.html",
                {"message": f"Errors on Card - not saved<br>{form.errors}"},
            )

        # Create a new system card each time we save it so user can go back if they mess it up
        new_system_card = form.save(commit=False)
        new_system_card.user = system_card.user
        new_system_card.card_name = request.POST.get("card_new_name")

        new_system_card.save()
        response = render(
            request,
            "accounts/system_card/system_card_save.html",
            {"message": "Card saved"},
        )

        if system_card.card_name != new_system_card.card_name:
            # Tell htmx to redirect as we have changed the URL
            response["HX-Redirect"] = reverse(
                "accounts:system_card_edit",
                kwargs={"system_card_name": new_system_card.card_name},
            )

        _save_card_as_template(system_card, "standard_american.txt")

        return response

    form = SystemCardForm(instance=system_card)

    return render(
        request,
        "accounts/system_card/system_card.html",
        {
            "editable": True,
            "form": form,
            "system_card": system_card,
            "template": "base.html",
        },
    )


def create_pdf_system_card(request, system_card_name):
    """Generate a PDF of the system card"""

    # File-like object
    buffer = io.BytesIO()

    # Create the PDF object
    width, height = A4
    pdf = canvas.Canvas(buffer, pagesize=A4)

    pdf = _fill_in_system_card(pdf, system_card_name, width, height)

    # Close it off
    pdf.showPage()
    pdf.save()

    # rewind and return the file
    buffer.seek(0)
    # return FileResponse(buffer, as_attachment=True, filename='hello.pdf')
    return FileResponse(buffer, filename="hello.pdf")


def _fill_in_system_card(pdf, system_card_name, width, height):
    """ugly code to file in the system card for the pdf"""

    pdf.setFont("Times-Roman", 20)

    # Draw on the canvas
    pdf.drawString(50, height - 50, "AUSTRALIAN BRIDGE")
    pdf.drawString(50, height - 80, "FEDERATION")

    return pdf
