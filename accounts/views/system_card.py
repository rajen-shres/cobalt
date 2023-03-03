import io

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, FileResponse
from django.shortcuts import render, get_object_or_404
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from accounts.forms import SystemCardForm
from accounts.models import SystemCard


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

    system_card = get_object_or_404(SystemCard, pk=system_card_id)
    form = SystemCardForm(instance=system_card)

    return render(
        request,
        "accounts/system_card/system_card.html",
        {"all_responses": all_responses, "form": form, "editable": False},
    )


@login_required
def system_card_edit(request, system_card_id):
    """Edit a system card"""

    system_card = get_object_or_404(SystemCard, pk=system_card_id)
    if system_card.user != request.user:
        return HttpResponse("Access Denied. You are not the owner of this system card.")

    if request.method == "POST":
        print("Posted")
        form = SystemCardForm(request.POST)
        if form.is_valid():
            form.save()
            return HttpResponse("Card saved")
        else:
            return HttpResponse(f"Errors on Card - not saved<br>{form.errors}")

    form = SystemCardForm(instance=system_card)

    return render(
        request,
        "accounts/system_card/system_card.html",
        {"editable": True, "form": form, "system_card": system_card},
    )


def create_pdf_system_card(request, system_card_id):
    """Generate a PDF of the system card"""

    # File-like object
    buffer = io.BytesIO()

    # Create the PDF object
    width, height = A4
    pdf = canvas.Canvas(buffer, pagesize=A4)

    pdf = _fill_in_system_card(pdf, system_card_id, width, height)

    # Close it off
    pdf.showPage()
    pdf.save()

    # rewind and return the file
    buffer.seek(0)
    # return FileResponse(buffer, as_attachment=True, filename='hello.pdf')
    return FileResponse(buffer, filename="hello.pdf")


def _fill_in_system_card(pdf, system_card_id, width, height):
    """ugly code to file in the system card for the pdf"""

    pdf.setFont("Times-Roman", 20)

    # Draw on the canvas
    pdf.drawString(50, height - 50, "AUSTRALIAN BRIDGE")
    pdf.drawString(50, height - 80, "FEDERATION")

    return pdf
