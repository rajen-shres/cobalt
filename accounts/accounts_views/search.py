from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from accounts.models import User
from cobalt.settings import (
    RBAC_EVERYONE,
    TBA_PLAYER,
    GLOBAL_TITLE,
    GLOBAL_ORG,
    ABF_USER,
)


@login_required()
def member_search_ajax(request):
    """Ajax member search function. Used by the generic member search.

    Used to search for members by the Member to Member transfer part of Payments.
    Currently very specific to payments. Could be made more generic if other
    parts of the system need a search function.

    Args:
        lastname - partial lastname to search for. Wild cards the ending.
        firstname - partial firstname to search for. Wild cards the ending.
        search_id - used if page has multiple user searches. We just pass this
        through. Optional.

    Returns:
        HttpResponse - either a message or a list of users in HTML format.
    """

    msg = ""

    if request.method == "GET":

        if "search_id" in request.GET:
            search_id = request.GET.get("search_id")
        else:
            search_id = None

        if "lastname" in request.GET:
            search_last_name = request.GET.get("lastname")
        else:
            search_last_name = None

        if "firstname" in request.GET:
            search_first_name = request.GET.get("firstname")
        else:
            search_first_name = None

        # flag to include the user in the output
        if "include_me" in request.GET:
            exclude_list = [RBAC_EVERYONE, TBA_PLAYER]
        else:
            exclude_list = [request.user.id, RBAC_EVERYONE, TBA_PLAYER]

        if search_first_name and search_last_name:
            members = User.objects.filter(
                first_name__istartswith=search_first_name,
                last_name__istartswith=search_last_name,
            ).exclude(pk__in=exclude_list)
        elif search_last_name:
            members = User.objects.filter(
                last_name__istartswith=search_last_name
            ).exclude(pk__in=exclude_list)
        else:
            members = User.objects.filter(
                first_name__istartswith=search_first_name
            ).exclude(pk__in=exclude_list)

        if request.is_ajax:
            if members.count() > 30:
                msg = "Too many results (%s)" % members.count()
                members = None
            elif members.count() == 0:
                msg = f"No matches found. Have they registered for {GLOBAL_TITLE}? Registration is free."
            html = render_to_string(
                template_name="accounts/search/search_results_ajax.html",
                context={"members": members, "msg": msg, "search_id": search_id},
            )

            data_dict = {"data": html}

            return JsonResponse(data=data_dict, safe=False)

    return render(
        request,
        "accounts/search/search_results_ajax.html",
        context={"members": members, "msg": msg},
    )


@login_required()
def system_number_search_ajax(request):
    """Ajax system_number search function. Used by the generic member search.

    Args:
        system_number - exact number to search for

    Returns:
        HttpResponse - either a message or a list of users in HTML format.
    """

    if request.method != "GET":
        return JsonResponse(data={"error": "Invalid request"})

    exclude_list = [request.user.system_number, RBAC_EVERYONE, TBA_PLAYER]

    if "system_number" in request.GET:
        system_number = request.GET.get("system_number")
        member = User.objects.filter(system_number=system_number).first()
    else:
        system_number = None
        member = None

    if member and member.system_number not in exclude_list:
        status = "Success"
        msg = "Found member"
        member_id = member.id
    else:
        status = "Not Found"
        msg = f"No matches found for that {GLOBAL_ORG} number. Check they have registered for <strong>{GLOBAL_TITLE}</strong>. Registration is free."
        member_id = 0

    data = {"member_id": member_id, "status": status, "msg": msg}

    data_dict = {"data": data}
    return JsonResponse(data=data_dict, safe=False)


@login_required()
@require_POST
def member_search_htmx(request):
    """Search on user first and last name.

    The goal of the member search is to finally replace the included search with a hidden user_id input field,
    the users name and a button to search again. Alternatively, a callback can be provided which will be called
    if/when a user is selected.

    All parameters are passed through in the request:

    search_id:     optional identifier, required if there are multiple user searches on same page, must be unique
                   but can be anything. Gets appended to any DOM objects that should be unique on the page. This is
                   also used as the prefix for the final user_id field if user_id_field is not specified.
    user_id_field: Optional. At the end, if we find a matching user we will create an element for the user_id and
                   an element for the user name to display. The user_id_field will be used as the name of the
                   user_id input. If not specified then member{search_id} is used.
    include_me:    Flag to include the logged in user in the search. Default is no.
    callback:      Optional. If provided then this will be called when a member is picked.
    """

    # Get parameters
    search_id = request.POST.get("search_id", "")
    user_id_field = request.POST.get("user_id_field", "")
    callback = request.POST.get("callback", "")

    # Get partial first name to search for from form
    last_name_search = request.POST.get("last_name_search")
    first_name_search = request.POST.get("first_name_search")

    # If user enters data and then deletes it we can get nothing through - ignore
    if not last_name_search and not first_name_search:
        return HttpResponse("")

    # ignore system accounts
    include_me, exclude_list = _get_exclude_list_for_search(request)

    if last_name_search and first_name_search:
        name_list = (
            User.objects.filter(last_name__istartswith=last_name_search)
            .filter(first_name__istartswith=first_name_search)
            .exclude(pk__in=exclude_list)
        )
    elif last_name_search:
        name_list = User.objects.filter(
            last_name__istartswith=last_name_search
        ).exclude(pk__in=exclude_list)
    else:
        name_list = User.objects.filter(
            first_name__istartswith=first_name_search
        ).exclude(pk__in=exclude_list)

    # See if there is more data
    more_data = False
    if name_list.count() > 10:
        more_data = True
        name_list = name_list[:10]

    return render(
        request,
        "accounts/search/member_search_htmx.html",
        {
            "name_list": name_list,
            "more_data": more_data,
            "search_id": search_id,
            "user_id_field": user_id_field,
            "include_me": include_me,
            "callback": callback,
        },
    )


@login_required()
@require_POST
def system_number_search_htmx(request):
    """Search on system number"""

    # Get parameters
    search_id = request.POST.get("search_id", "")
    callback = request.POST.get("callback", "")
    system_number = request.POST.get("system_number")

    if system_number == "":
        return HttpResponse(
            "<span class='cobalt-form-error''>Enter a number to look up, or type in the name fields</span>"
        )

    # ignore system accounts
    include_me, exclude_list = _get_exclude_list_for_search(request)

    member = (
        User.objects.filter(system_number=system_number)
        .exclude(pk__in=exclude_list)
        .first()
    )

    print("sys num", system_number)

    if member:
        return render(
            request,
            "accounts/search/name_match_htmx.html",
            {
                "member": member,
                "search_id": search_id,
                "user_id_field": system_number,
                "include_me": include_me,
                "callback": callback,
            },
        )
    else:
        return HttpResponse("No match found")


@login_required()
@require_POST
def member_match_htmx(request):
    """show member details when a user picks from the list of matches"""

    # Get parameters
    member_id = request.POST.get("member_id")
    search_id = request.POST.get("search_id", "")
    user_id_field = request.POST.get("user_id_field", "")
    callback = request.POST.get("callback", "")

    # ignore system accounts
    include_me, exclude_list = _get_exclude_list_for_search(request)

    member = User.objects.filter(pk=member_id).exclude(pk__in=exclude_list).first()

    if member:
        return render(
            request,
            "accounts/search/name_match_htmx.html",
            {
                "member": member,
                "search_id": search_id,
                "user_id_field": user_id_field,
                "include_me": include_me,
                "callback": callback,
            },
        )
    else:
        return HttpResponse("No match found")


@login_required()
@require_POST
def member_match_summary_htmx(request):
    """show outcome from search"""

    # Get parameters
    member_id = request.POST.get("member_id")
    search_id = request.POST.get("search_id", "")
    user_id_field = request.POST.get("user_id_field", "")
    include_me = bool(request.POST.get("include_me"))

    member = get_object_or_404(User, pk=member_id)

    return render(
        request,
        "accounts/search/name_match_summary_htmx.html",
        {
            "member": member,
            "search_id": search_id,
            "user_id_field": user_id_field,
            "include_me": include_me,
        },
    )


@login_required()
def member_detail_m2m_ajax(request):
    """Returns basic public info on a member. ONLY USED BY MEMBER TRANSFER. REPLACE.

    Ajax call to get basic info on a member. Will return an empty json array
    if the member number is invalid.

    Args:
        member_id - member number

    Returns:
        Json array: member, clubs,  global org name.
    """

    if request.method == "GET" and "member_id" in request.GET:
        member_id = request.GET.get("member_id")
        member = get_object_or_404(User, pk=member_id)
        if request.is_ajax:
            global_org = settings.GLOBAL_ORG
            html = render_to_string(
                template_name="accounts/search/member_ajax.html",
                context={
                    "member": member,
                    "global_org": global_org,
                },
            )
            data_dict = {"data": html}
            return JsonResponse(data=data_dict, safe=False)
    return JsonResponse(data={"error": "Invalid request"})


@login_required()
def member_details_ajax(request):
    """Returns basic public info on a member for the generic member search.

    Ajax call to get basic info on a member. Will return an empty json array
    if the member number is invalid.

    Args:
        member_id - member number
        search_id - used if page has multiple user searches. We just pass this
        through. Optional.

    Returns:
        Json array: member, clubs,  global org name.
    """

    if request.method == "GET":

        if "search_id" in request.GET:
            search_id = request.GET.get("search_id")
        else:
            search_id = None

        if "member_id" in request.GET:
            member_id = request.GET.get("member_id")
            member = get_object_or_404(User, pk=member_id)
            if request.is_ajax:
                global_org = settings.GLOBAL_ORG
                html = render_to_string(
                    template_name="accounts/search/member_details_ajax.html",
                    context={
                        "member": member,
                        "global_org": global_org,
                        "search_id": search_id,
                    },
                )
                data_dict = {
                    "data": html,
                    "member": "%s" % member,
                    "pic": f"{member.pic}",
                }
                return JsonResponse(data=data_dict, safe=False)
    return JsonResponse(data={"error": "Invalid request"})


@login_required()
def search_ajax(request):
    """Ajax member search function. ONLY USED BY MEMBER TRANSFER. REPLACE.

    Used to search for members by the Member to Member transfer part of Payments.
    Currently very specific to payments. Could be made more generic if other
    parts of the system need a search function.

    Args:
        lastname - partial lastname to search for. Wild cards the ending.
        firstname - partial firstname to search for. Wild cards the ending.

    Returns:
        HttpResponse - either a message or a list of users in HTML format.
    """

    msg = ""

    if request.method == "GET":

        if "lastname" in request.GET:
            search_last_name = request.GET.get("lastname")
        else:
            search_last_name = None

        if "firstname" in request.GET:
            search_first_name = request.GET.get("firstname")
        else:
            search_first_name = None

        if search_first_name and search_last_name:
            members = User.objects.filter(
                first_name__istartswith=search_first_name,
                last_name__istartswith=search_last_name,
            ).exclude(pk=request.user.id)
        elif search_last_name:
            members = User.objects.filter(
                last_name__istartswith=search_last_name
            ).exclude(pk=request.user.id)
        else:
            members = User.objects.filter(
                first_name__istartswith=search_first_name
            ).exclude(pk=request.user.id)

        if request.is_ajax:
            if members.count() > 30:
                msg = "Too many results (%s)" % members.count()
                members = None
            elif members.count() == 0:
                msg = f"No matches found. Have they registered for {GLOBAL_TITLE}? Registration is free."
            html = render_to_string(
                template_name="accounts/search/search_results.html",
                context={"members": members, "msg": msg},
            )

            data_dict = {"data": html}

            return JsonResponse(data=data_dict, safe=False)

    return render(
        request,
        "accounts/search/search_results.html",
        context={"members": members, "msg": msg},
    )


def _get_exclude_list_for_search(request):
    """get the exclude list. System IDs and this user are excluded unless include_me is set"""

    # Check for include_me flag, otherwise don't include current user
    include_me = bool(request.POST.get("include_me"))

    # ignore system accounts
    exclude_list = [RBAC_EVERYONE, TBA_PLAYER, ABF_USER]

    # Ignore this user unless overridden
    if not include_me:
        exclude_list.append(request.user.id)

    return include_me, exclude_list
