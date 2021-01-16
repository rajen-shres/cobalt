from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from .models import (
    RBACGroup,
    RBACUserGroup,
    RBACGroupRole,
    RBACAdminUserGroup,
    RBACAdminGroup,
    RBACAdminGroupRole,
    RBACAdminTree,
    RBACAppModelAction,
    RBACModelDefault,
)
from accounts.models import User
from .core import (
    rbac_add_user_to_group,
    rbac_user_is_group_admin,
    rbac_access_in_english,
    rbac_admin_all_rights,
    rbac_get_admins_for_group,
    rbac_user_role_list,
    rbac_user_has_role,
    rbac_user_is_role_admin,
    rbac_user_has_role_explain,
    rbac_get_groups_for_role,
    rbac_user_blocked_for_model,
    rbac_user_allowed_for_model,
    role_to_parts,
    rbac_get_users_with_role,
    rbac_admin_tree_access,
)
from cobalt.settings import TIME_ZONE
from .forms import AddGroup
from django.contrib import messages
from django.utils import timezone
from organisations.models import Organisation
import os
import datetime
import pytz


@login_required
def rbac_forbidden(request, role):
    """RBAC screen for fobidden access - gives the user more info than a
    normal error screen"""

    groups = rbac_get_groups_for_role(role)

    return render(request, "rbac/forbidden.html", {"role": role, "groups": groups})


@login_required
def main_admin_screen(request):
    """ Shows the main admin screen - maybe shouldn't live in RBAC """

    payments_admin = rbac_user_role_list(request.user, "payments", "manage")
    org_list = []
    for item in payments_admin:
        org_list.append(item[0])

    orgs = Organisation.objects.filter(pk__in=org_list)

    payments_site_admin = rbac_user_has_role(request.user, "payments.global.view")

    events_site_admin = rbac_user_has_role(request.user, "events.global.edit")
    email_site_admin = rbac_user_has_role(request.user, "notifications.admin.view")

    # Get build time of this release
    TZ = pytz.timezone(TIME_ZONE)

    stat_time = os.stat("__init__.py").st_mtime
    utc_build_date = datetime.datetime.fromtimestamp(stat_time)
    # build_date = timezone.localtime(utc_build_date, TZ)
    build_date = TZ.localize(utc_build_date)

    return render(
        request,
        "rbac/main-admin-screen.html",
        {
            "payments_admin": orgs,
            "payments_site_admin": payments_site_admin,
            "events_site_admin": events_site_admin,
            "email_site_admin": email_site_admin,
            "build_date": build_date,
        },
    )


@login_required
def view_screen(request):
    """ Shows the user what roles they have in RBAC """

    groups = RBACGroup.objects.filter(rbacusergroup__member=request.user)

    # split by type
    # data = {}
    # for user_group in user_groups:
    #     if user_group.group.name_qualifier in data:
    #         data[user_group.group.name_qualifier].append(user_group.group)
    #     else:
    #         data[user_group.group.name_qualifier] = [user_group.group]
    #
    # group_list = user_groups.values_list("group")
    roles = RBACGroupRole.objects.filter(group__in=groups)

    english = rbac_access_in_english(request.user)

    return render(
        request,
        "rbac/view-screen.html",
        {"groups": groups, "english": english, "roles": roles},
    )


def generic_tree_builder(groups, detail_link=None, html_type="href"):
    """function to build an rbac tree for use with the tree viewer.

    Args:
        groups - queryset of RBACGroup or RBACAdminGroup
        detail_link - str of link to follow
        html_type - str to specify whether to generate <a> or <button>

    Returns:
        str - HTML string to insert into page

    build a list of the tree. We want to turn:
     abf.people.fred          (id=34)
     abf.people.john          (id=45)
     abf.animals.dogs.rover   (id=2)
     abf.animals.cats.felix   (id=21)

    into:
     items["abf"]=["people", "animals"]
     items["abf.people"]=["fred", "john"]
     items["abf.people.fred"]=34
     items["abf.people.john"]=45
     items["abf.animals"]=["dogs", "cats"]
     items["abf.animals.dogs"]=["rover"]
     items["abf.animals.cats"]=["felix"]
     items["abf.animals.dogs.rover"]=2
     items["abf.animals.cats.felix"]=21
    """

    items = {}
    items_description = {}
    for group in groups:
        line = f"{group.name_qualifier}.{group.name_item}"
        parts = line.split(".")
        for i in range(1, len(parts) + 1):

            string = ".".join(parts[:i])

            if i == len(parts):  # end of line
                child = group.id
                items_description[group.id] = group.description

            else:  # more left
                child = parts[i]

            if string in items:
                if child not in items[string]:
                    items[string].append(child)
            else:
                items[string] = [child]

    # sort the dictionary on keys
    sorted_items = dict(sorted(items.items()))

    """ generate html - loop through the sorted dictionary and do 3 things:
     1) if there is more below create a new ul
     2) if we are the end of the tree (contents is an integer) print the link to the details
     3) manage the stack so we close the right number of uls
     """

    html_tree = ""
    depth = []
    for key, value in sorted_items.items():
        this_level = ".".join(key.split(".")[:-1])  # eg we are a.b.c level=a.b

        # are we at the top?
        if len(depth) == 0:
            depth.append(this_level)

        # at the same level?
        elif this_level == depth[-1]:
            pass

        # gone down?
        elif this_level.find(depth[-1]) == 0:
            depth.append(this_level)

        # gone up? If so how far?
        else:
            while len(depth) > 0:
                if depth[-1] == this_level:
                    break
                else:
                    depth = depth[:-1]
                    html_tree += "</ul>\n"

        # now process line
        last_part = key.split(".")[-1]
        if isinstance(value[0], int):
            if html_type == "href":
                html_tree += "<li><a href='%s%s/'>%s (%s)</a></li>\n" % (
                    detail_link,
                    value[0],
                    last_part,
                    items_description[value[0]],
                )
            elif html_type == "button":
                html_tree += (
                    "<li>%s (%s) <button value='%s' class='tree-btn cobalt-rbac-tree btn btn-sm btn-primary'>Use</button></li>\n"
                    % (last_part, items_description[value[0]], key)
                )
        else:
            html_tree += (
                "<li><span class='caret'>%s</span><ul class='nested'>\n" % last_part
            )

    return html_tree


def generic_tree_screen(request, groups, detail_link, title):
    """ Show full RBAC Tree for RBAC or Admin """

    html_tree = generic_tree_builder(groups, detail_link)

    return render(
        request, "rbac/tree-screen.html", {"html_tree": html_tree, "title": title}
    )


@login_required
def tree_screen(request):
    """ Show full RBAC Tree """
    # Get groups
    groups = RBACGroup.objects.all().order_by("name_qualifier")

    return generic_tree_screen(request, groups, "/rbac/group/view/", "Tree Viewer")


@login_required
def admin_tree_screen(request):
    """ Show full RBAC Admin Tree """
    # Get groups
    groups = RBACAdminGroup.objects.all().order_by("name_qualifier")

    return generic_tree_screen(
        request, groups, "/rbac/admin/group/view/", "Admin Tree Viewer"
    )


@login_required
def role_view_screen(request):
    """ Show Roles """
    # Get groups
    roles = RBACAppModelAction.objects.all().order_by("app", "model", "valid_action")
    defaults = RBACModelDefault.objects.all().order_by("app", "model")

    return render(
        request, "rbac/role_view.html", {"roles": roles, "defaults": defaults}
    )


@login_required
def group_view(request, group_id):
    """ view to show details of a group """

    group = get_object_or_404(RBACGroup, pk=group_id)
    users = RBACUserGroup.objects.filter(group=group)
    roles = RBACGroupRole.objects.filter(group=group)
    is_admin = rbac_user_is_group_admin(request.user, group)
    admins = rbac_get_admins_for_group(group)
    return render(
        request,
        "rbac/group_view.html",
        {
            "users": users,
            "roles": roles,
            "group": group,
            "is_admin": is_admin,
            "admins": admins,
        },
    )


@login_required
def admin_group_view(request, group_id):
    """ view to show details of an admin group """

    group = get_object_or_404(RBACAdminGroup, pk=group_id)
    users = RBACAdminUserGroup.objects.filter(group=group)
    roles = RBACAdminGroupRole.objects.filter(group=group)
    trees = RBACAdminTree.objects.filter(group=group)
    user_list = users.values_list("member", flat=True)
    if request.user.id in user_list:
        is_admin = True
    else:
        is_admin = False
    return render(
        request,
        "rbac/admin_group_view.html",
        {
            "users": users,
            "roles": roles,
            "group": group,
            "trees": trees,
            "is_admin": is_admin,
        },
    )


@login_required
def group_delete(request, group_id):
    """ view to delete a group """

    group = get_object_or_404(RBACGroup, pk=group_id)
    if not rbac_user_is_group_admin(request.user, group):
        return HttpResponse("You are not an admin for this group")
    else:
        if request.method == "POST":
            group.delete()
            messages.success(
                request,
                "Group successfully deleted.",
                extra_tags="cobalt-message-success",
            )
            return redirect("rbac:access_screen")
        return render(request, "rbac/group_delete.html", {"group": group})


@login_required
def admin_group_delete(request, group_id):
    """ view to delete an admin group """

    group = get_object_or_404(RBACAdminGroup, pk=group_id)
    if not rbac_user_is_group_admin(request.user, group):
        return HttpResponse("You are not an admin for this group")
    else:
        if request.method == "POST":
            group.delete()
            messages.success(
                request,
                "Admin Group successfully deleted.",
                extra_tags="cobalt-message-success",
            )
            return redirect("rbac:access_screen")
        return render(request, "rbac/admin_group_delete.html", {"group": group})


@login_required
def group_create(request):
    """ view to create a new group """

    if request.method == "POST":
        form = AddGroup(request.POST, user=request.user, environment="rbac")
        if form.is_valid():
            group = RBACGroup(
                name_item=form.cleaned_data["name_item"],
                name_qualifier=form.cleaned_data["name_qualifier"],
                description=form.cleaned_data["description"],
                created_by=request.user,
            )
            group.save()
            messages.success(
                request,
                "Group successfully created.",
                extra_tags="cobalt-message-success",
            )
            if form.cleaned_data["add_self"]:
                rbac_add_user_to_group(request.user, group)
                messages.success(
                    request,
                    "Added you to new group.",
                    extra_tags="cobalt-message-success",
                )
            return redirect("rbac:group_edit", group_id=group.id)

    else:
        form = AddGroup(user=request.user, environment="rbac")
    return render(request, "rbac/group_create.html", {"form": form})


@login_required
def admin_group_create(request):
    """ view to create a new admin group """

    if request.method == "POST":
        form = AddGroup(request.POST, user=request.user, environment="admin")
        if form.is_valid():
            group = RBACAdminGroup(
                name_item=form.cleaned_data["name_item"],
                name_qualifier=form.cleaned_data["name_qualifier"],
                description=form.cleaned_data["description"],
                created_by=request.user,
            )
            group.save()
            messages.success(
                request,
                "Admin Group successfully created.",
                extra_tags="cobalt-message-success",
            )
            if form.cleaned_data["add_self"]:
                mapping = RBACAdminUserGroup(group=group, member=request.user)
                mapping.save()
                messages.success(
                    request,
                    "Added you to group %s." % group,
                    extra_tags="cobalt-message-success",
                )
            return redirect("rbac:admin_group_view", group_id=group.id)

    else:
        form = AddGroup(user=request.user, environment="admin")
    return render(request, "rbac/admin_group_create.html", {"form": form})


@login_required
def group_edit(request, group_id):
    """ view to edit a group """

    group = get_object_or_404(RBACGroup, pk=group_id)
    if not rbac_user_is_group_admin(request.user, group):
        return HttpResponse("You are not an admin for this group")
    else:
        if request.method == "POST":
            form = AddGroup(request.POST, user=request.user, environment="rbac")
            if form.is_valid():
                group.name_item = form.cleaned_data["name_item"]
                group.description = form.cleaned_data["description"]
                group.save()
                messages.success(
                    request,
                    "Group successfully updated.",
                    extra_tags="cobalt-message-success",
                )
            else:
                print(form.errors)
        else:
            form = AddGroup(user=request.user, environment="rbac")
            form.fields["name_item"].initial = group.name_item
            form.fields["description"].initial = group.description

        users = RBACUserGroup.objects.filter(group=group)
        admin_roles = rbac_admin_all_rights(request.user)
        roles = RBACGroupRole.objects.filter(group=group)

        return render(
            request,
            "rbac/group_edit.html",
            {
                "form": form,
                "group": group,
                "users": users,
                "roles": roles,
                "admin_roles": admin_roles,
            },
        )


@login_required
def admin_group_edit(request, group_id):
    """ view to edit an admin group """

    group = get_object_or_404(RBACAdminGroup, pk=group_id)

    # could use rbac_user_is_admin_for_admin_group but we need the
    # users anyway so more efficient to do it here

    users = RBACAdminUserGroup.objects.filter(group=group)
    user_list = users.values_list("member", flat=True)
    if request.user.id not in user_list:
        return HttpResponse("You are not an admin for this admin group")

    if request.method == "POST":
        form = AddGroup(request.POST, user=request.user, environment="admin")
        if form.is_valid():
            group.name_item = form.cleaned_data["name_item"]
            group.description = form.cleaned_data["description"]
            group.save()
            messages.success(
                request,
                "Admin Group successfully updated.",
                extra_tags="cobalt-message-success",
            )
        else:
            print(form.errors)
    else:
        form = AddGroup(user=request.user, environment="admin")
        form.fields["name_item"].initial = group.name_item
        form.fields["description"].initial = group.description

    roles = RBACAdminGroupRole.objects.filter(group=group)
    trees = RBACAdminTree.objects.filter(group=group)
    admin_roles = rbac_admin_all_rights(request.user)
    return render(
        request,
        "rbac/admin_group_edit.html",
        {
            "form": form,
            "group": group,
            "users": users,
            "roles": roles,
            "trees": trees,
            "admin_roles": admin_roles,
        },
    )


@login_required
def rbac_admin(request):
    """ shows the admin groups a user is in """

    group_list = RBACAdminUserGroup.objects.filter(member=request.user).values_list(
        "group"
    )
    groups = RBACAdminGroup.objects.filter(id__in=group_list)

    roles = RBACAdminGroupRole.objects.filter(group__in=group_list)

    group_list = RBACAdminUserGroup.objects.filter(member=request.user).values_list(
        "group"
    )
    trees = RBACAdminTree.objects.filter(group__in=group_list)

    return render(
        request,
        "rbac/admin-screen.html",
        {"groups": groups, "roles": roles, "trees": trees},
    )


@login_required
def rbac_tests(request):
    """ easy way to underlying functions. Test only """

    ans = None
    userid = None
    user = None
    text = ""
    group = None
    role = None
    model = None
    last_query = None

    if request.method == "POST":
        userid = request.POST.get("id_user")
        if userid:
            user = get_object_or_404(User, pk=userid)
        text = request.POST.get("id_text", "")

        if "user_has_role" in request.POST:
            ans = rbac_user_has_role(user, text)
            if not ans:
                ans = "False"  # bool -> string so it shows on screen
            last_query = "User Has Role"
            role = text

        if "user_has_role_explain" in request.POST:
            ans = rbac_user_has_role_explain(user, text)
            last_query = "User Has Role Explain"
            role = text

        if "user_access_in_english" in request.POST:
            ans = rbac_access_in_english(user)
            ans = "\n".join(ans)
            last_query = "User Access in English"

        if "user_blocked_for_model" in request.POST:
            (app, model, model_instance, action) = role_to_parts(text)
            ans = rbac_user_blocked_for_model(user, app, model, action)
            if not ans:
                ans = "Nothing found."
            last_query = "User Blocked for Model"
            role = text

        if "user_allowed_for_model" in request.POST:
            (app, model, model_instance, action) = role_to_parts(text)
            (everything, ans) = rbac_user_allowed_for_model(user, app, model, action)
            if everything:
                ans = "Allowed for all models"
            else:
                if not ans:
                    ans = "Nothing found."
            last_query = "User Allowed for Model"
            model = text

        if "get_users_with_role" in request.POST:
            users = rbac_get_users_with_role(text)
            if users:
                ans = ""
                for user_inst in users:
                    ans += "%s\n" % user_inst
            else:
                ans = "Nothing found"
            last_query = "Get Users With Role"
            role = text
            user = None
            user = None

        if "get_admins_for_group" in request.POST:
            last_query = "Get Admins for Group"
            parts = text.split(".")
            name_qualifier = ".".join(parts[:-1])
            name_item = parts[-1]
            group = RBACGroup.objects.filter(
                name_qualifier=name_qualifier, name_item=name_item
            ).first()
            if group:
                admins = rbac_get_admins_for_group(group)
                ans = ""
                for admin in admins:
                    ans += "%s\n" % admin.member
            else:
                ans = "Group not found"
            group = text

        if "user_is_group_admin" in request.POST:
            last_query = "User Is Group Admin"
            parts = text.split(".")
            name_qualifier = ".".join(parts[:-1])
            name_item = parts[-1]
            group = RBACGroup.objects.filter(
                name_qualifier=name_qualifier, name_item=name_item
            ).first()
            if group:
                ans = rbac_user_is_group_admin(user, group)
                if not ans:
                    ans = "False"  # bool -> string so it shows on screen
            else:
                ans = "Group not found"
            group = text

        if "user_is_role_admin" in request.POST:
            ans = rbac_user_is_role_admin(user, text)
            if not ans:
                ans = "False"
            last_query = "User Is Role Admin"
            role = text

        if "admin" in request.POST:
            last_query = "Admin"
            rights = rbac_admin_all_rights(user)
            ans = "\n".join(rights)
            if not ans:
                ans = "Nothing found."

        if "admin-tree" in request.POST:
            last_query = "Admin Tree"
            rights = rbac_admin_tree_access(user)
            ans = "\n".join(rights)
            if not ans:
                ans = "Nothing found."

    # Get trees
    groups = RBACGroup.objects.all().order_by("name_qualifier")
    tree = generic_tree_builder(groups, html_type="button")
    admin_groups = RBACAdminGroup.objects.all().order_by("name_qualifier")
    admin_tree = generic_tree_builder(admin_groups, html_type="button")

    # get models
    models = RBACModelDefault.objects.all().order_by("app", "model")

    # Get roles
    roles = RBACAppModelAction.objects.all().order_by("app", "model", "valid_action")

    # format ans for the Sweet Alert popup
    # if ans.type() == 'str':
    #     ans_swal = ans.replace("'", "")
    #     ans_swal = ans_swal.replace("\n", "\\\n")
    # else:
    ans_swal = ans

    return render(
        request,
        "rbac/tests.html",
        {
            "ans": ans,
            "ans_swal": ans_swal,
            "member_id": userid,
            "text": text,
            "tree": tree,
            "admin_tree": admin_tree,
            "models": models,
            "roles": roles,
            "group": group,
            "role": role,
            "model": model,
            "user": user,
            "last_query": last_query,
        },
    )
