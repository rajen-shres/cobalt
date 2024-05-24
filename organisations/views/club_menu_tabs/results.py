import logging
import xml

from django.db.transaction import atomic
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.datetime_safe import datetime

from accounts.views.core import get_email_address_and_name_from_system_number
from cobalt.settings import COBALT_HOSTNAME
from notifications.models import Snooper, BatchID
from notifications.views.core import (
    create_rbac_batch_id,
    custom_sender,
    send_cobalt_email_with_template,
    club_default_template,
)
from organisations.decorators import check_club_menu_access
from organisations.forms import ResultsFileForm, ResultsEmailMessageForm
from organisations.models import OrgEmailTemplate
from organisations.views.club_menu import tab_results_htmx
from results.models import ResultsFile
from results.views.usebio import (
    parse_usebio_file,
    create_player_records_from_usebio_format_pairs,
)

logger = logging.getLogger("cobalt")


def upload_results_file_valid(request, form, club):
    """sub of upload_results_file_htmx. This is separated out so the tests can call it directly"""

    results_file = form.save(commit=False)

    # Add data
    results_file.organisation = club
    results_file.uploaded_by = request.user
    results_file.save()

    # Try to parse the file
    try:
        usebio = parse_usebio_file(results_file)

    except xml.parsers.expat.ExpatError:
        results_file.delete()
        logger.error(f"Invalid file format - user: {request.user}")
        return tab_results_htmx(request, message="Invalid file format")

    results_file.description = usebio.get("EVENT").get("EVENT_DESCRIPTION")

    event_date_str = usebio.get("EVENT").get("DATE")

    # Try to get the date from the file (being consistent with player records
    try:
        event_date = datetime.strptime(event_date_str, "%d/%m/%Y").date()
    except ValueError:
        try:
            event_date = datetime.strptime(event_date_str, "%d-%m-%Y").date()
        except ValueError:
            event_date = datetime.today()

    results_file.event_date = event_date
    results_file.save()

    # Create the player records so people know the results are there
    create_player_records_from_usebio_format_pairs(results_file, usebio)

    return tab_results_htmx(request, message="New results successfully uploaded")


@check_club_menu_access(check_sessions=True)
@atomic()
def upload_results_file_htmx(request, club):
    """Upload a new results file"""

    form = ResultsFileForm(request.POST, request.FILES)

    if form.is_valid():
        return upload_results_file_valid(request, form, club)
    return tab_results_htmx(request, message="Invalid data provided")


@check_club_menu_access(check_sessions=True)
def toggle_result_publish_state_htmx(request, club):
    """change to published / pending"""

    results_file_id = request.POST.get("results_file_id")
    results_file = get_object_or_404(ResultsFile, pk=results_file_id)

    if results_file.organisation != club:
        return HttpResponse("Access Denied")

    if results_file.status == ResultsFile.ResultsStatus.PENDING:
        results_file.status = ResultsFile.ResultsStatus.PUBLISHED
        if club.send_results_email:
            sent_email_count = _send_results_emails(results_file, club, request)
            message = f"{results_file.description} published, and {sent_email_count} players emailed"
        else:
            message = f"{results_file.description} published. No emails sent as your settings block this."
    else:
        results_file.status = ResultsFile.ResultsStatus.PENDING
        message = f"{results_file.description} changed to pending"

    results_file.save()

    return tab_results_htmx(request, message=message)


def _send_results_emails(results_file, club, request):
    """send the results email to users"""

    # Get file data as usebio format
    usebio = parse_usebio_file(results_file)

    # Get results template if we have one
    results_template = OrgEmailTemplate.objects.filter(
        organisation=club, template_name__iexact="Results"
    ).first()

    if not results_template:
        results_template = club_default_template(club) or OrgEmailTemplate(
            organisation=club
        )

    # set up context
    context = {
        "title": f"Your Results for {results_file.description}",
        "box_colour": results_template.box_colour,
        "box_font_colour": results_template.box_font_colour,
        "footer": results_template.footer,
    }

    reply_to = results_template.reply_to
    from_name = results_template.from_name
    if results_template.banner:
        context["img_src"] = results_template.banner.url
        # JPG debug
        # print(f"++++++ _send_results_emails url={results_template.banner.url}")

    # sender = f"{from_name}<donotreply@myabf.com.au>" if from_name else None
    sender = custom_sender(from_name)

    # Link to the results page
    link = reverse(
        "results:usebio_mp_pairs_results_summary_view",
        kwargs={"results_file_id": results_file.id},
    )

    # Create batch id to allow any admin for this club to view the email
    batch_id = create_rbac_batch_id(
        rbac_role=f"notifications.orgcomms.{club.id}.edit",
        user=request.user,
        organisation=club,
        batch_type=BatchID.BATCH_TYPE_RESULTS,
        description=context["title"],
        complete=True,
    )

    # Go through data, and email results to players
    for item in usebio["EVENT"]["PARTICIPANTS"]["PAIR"]:
        try:
            player_1_system_number = int(item["PLAYER"][0]["NATIONAL_ID_NUMBER"])
            player_2_system_number = int(item["PLAYER"][1]["NATIONAL_ID_NUMBER"])
            player_1_name = item["PLAYER"][0]["PLAYER_NAME"].title()
            player_2_name = item["PLAYER"][1]["PLAYER_NAME"].title()
        except TypeError:
            continue

        # get data
        position = int(item["PLACE"])
        # COB-807 - throwing exception if no masterpoints in file
        masterpoints = int(item.get("MASTER_POINTS_AWARDED", 0)) / 100.0
        percentage = item["PERCENTAGE"]

        for system_number in [player_1_system_number, player_2_system_number]:

            if system_number == player_1_system_number:
                partner = player_2_name
            else:
                partner = player_1_name

            # TODO: Load this higher up as a dictionary to reduce database calls
            email_address, first_name = get_email_address_and_name_from_system_number(
                system_number, club, requestor="results"
            )

            if email_address:

                # Build email body
                email_body = render_to_string(
                    "organisations/club_menu/results/results_email_summary.html",
                    {
                        "position": position,
                        "masterpoints": masterpoints,
                        "percentage": percentage,
                        "club": club,
                        "partner": partner,
                        "link": link,
                        "host": COBALT_HOSTNAME,
                        "club_message": club.results_email_message,
                    },
                )

                context["name"] = first_name
                context["email_body"] = email_body

                # COB-793 - add batch size - assumes 80% of players in event have emails and not opted out

                send_cobalt_email_with_template(
                    to_address=email_address,
                    context=context,
                    batch_id=batch_id,
                    template="system - club",
                    reply_to=reply_to,
                    sender=sender,
                    batch_size=int(
                        len(usebio["EVENT"]["PARTICIPANTS"]["PAIR"]) * 2 * 0.8
                    ),
                )

    # Count emails sent and update batch header
    batch_size = Snooper.objects.filter(batch_id=batch_id).count()

    batch = BatchID.objects.get(batch_id=batch_id)
    batch.batch_size = batch_size
    batch.save()

    return batch_size


@check_club_menu_access(check_sessions=True)
def delete_results_file_htmx(request, club):
    """delete a results file"""

    results_file_id = request.POST.get("results_file_id")
    results_file = get_object_or_404(ResultsFile, pk=results_file_id)

    if results_file.organisation != club:
        return HttpResponse("Access Denied")

    results_file.delete()

    return tab_results_htmx(request, message="Deleted")


@check_club_menu_access(check_sessions=True)
def update_results_email_message_htmx(request, club):
    """Update the club's results_email_message that is sent to players with all results"""

    # Check if we got empty string - need to strip left over html tags too
    if strip_tags(request.POST.get("results_email_message")) == "":
        club.results_email_message = ""
        club.save()
        return HttpResponse("Email message is now blank. No message will be sent.")

    # Handle non-blank email message
    form = ResultsEmailMessageForm(request.POST, instance=club)

    if form.is_valid():
        form.save()
        return HttpResponse("Email message saved")
    else:
        print(form.errors)
