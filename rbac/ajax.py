from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.template.loader import render_to_string
from .models import (
    RBACGroup,
    RBACAdminGroup,
    RBACUserGroup,
    RBACGroupRole,
    RBACAppModelAction,
    RBACAdminGroupRole,
)
from .core import (
    rbac_add_user_to_group,
    rbac_user_is_group_admin,
    rbac_user_is_admin_for_admin_group,
    rbac_remove_user_from_group,
    rbac_remove_admin_user_from_group,
    rbac_user_is_role_admin,
    rbac_add_role_to_group,
    rbac_add_user_to_admin_group,
    rbac_add_role_to_admin_group,
)
from accounts.models import User


@login_required
def group_to_user_ajax(request, group_id):
    """ Called by the admin page when a user selects a group.

    Takes the RBACGroup id and return the matching records from RBACUserGroup

    Args:
        request (HTTPRequest): standard request object.
        group_id (int): RBACGroup id to use for queries

    Returns:
        HTTPResponse: Ajax JSON object

    """
    group = RBACGroup.objects.get(pk=group_id)
    usergroups = RBACUserGroup.objects.filter(group=group)

    html = render_to_string(
        template_name="rbac/group-to-user.html", context={"usergroups": usergroups}
    )
    data_dict = {"data": html}
    return JsonResponse(data=data_dict, safe=False)


@login_required
def group_to_action_ajax(request, group_id):
    """ Called by the admin page when a user selects a group.

    Takes the RBACGroup id and return the matching records from RBACGroupRole

    Args:
        request (HTTPRequest): standard request object.
        group_id (int): RBACGroup id to use for queries

    Returns:
        HTTPResponse: Ajax JSON object

    """
    group = RBACGroup.objects.get(pk=group_id)
    roles = RBACGroupRole.objects.filter(group=group)

    html = render_to_string(
        template_name="rbac/group-to-action.html", context={"roles": roles}
    )
    data_dict = {"data": html}
    return JsonResponse(data=data_dict, safe=False)


@login_required()
def rbac_add_user_to_group_ajax(request):
    """ Ajax call to add a user to a group

    Args:
        request(HTTPRequest): standard request

    Returns:
        HTTPResponse: success, failure or error
    """

    if request.method == "GET":
        member_id = request.GET["member_id"]
        group_id = request.GET["group_id"]

        member = User.objects.get(pk=member_id)
        group = RBACGroup.objects.get(pk=group_id)

        if rbac_user_is_group_admin(request.user, group):
            rbac_add_user_to_group(member, group)
            msg = "Success"
        else:
            msg = "Access Denied"

    else:
        msg = "Invalid request"

    response_data = {}
    response_data["message"] = msg
    return JsonResponse({"data": response_data})


@login_required()
def rbac_add_user_to_admin_group_ajax(request):
    """ Ajax call to add a user to an admin group

    Args:
        request(HTTPRequest): standard request

    Returns:
        HTTPResponse: success, failure or error
    """

    if request.method == "GET":
        member_id = request.GET["member_id"]
        group_id = request.GET["group_id"]

        member = User.objects.get(pk=member_id)
        group = RBACAdminGroup.objects.get(pk=group_id)

        if rbac_user_is_admin_for_admin_group(request.user, group):
            rbac_add_user_to_admin_group(group, member)
            msg = "Success"
        else:
            msg = "Access Denied"

    else:
        msg = "Invalid request"

    response_data = {}
    response_data["message"] = msg
    return JsonResponse({"data": response_data})


@login_required()
def rbac_add_role_to_group_ajax(request):
    """ Ajax call to add a role to a group

    The user needs to be both a group admin (have access to this part of
    the tree), and also be an admin for the role thay are adding.

    Args:
        request(HTTPRequest): standard request

    Returns:
        HTTPResponse: success, failure or error
    """

    if request.method == "GET":
        group_id = request.GET["group_id"]
        app = request.GET["app"]
        model = request.GET["model"]
        model_id = request.GET["model_id"]
        action = request.GET["action"]
        rule_type = request.GET["rule_type"]

        if model_id == "None":
            model_id = None

        group = get_object_or_404(RBACGroup, pk=group_id)

        # must be both an admin for this group (able to edit this part of the tree)
        # and have rights to this role.
        if model_id:
            role_str = f"{app}.{model}.{model_id}"
        else:
            role_str = f"{app}.{model}"

        role_ok = rbac_user_is_role_admin(request.user, role_str)
        group_ok = rbac_user_is_group_admin(request.user, group)

        if role_ok and group_ok:

            rbac_add_role_to_group(
                group=group,
                app=app,
                model=model,
                model_id=model_id,
                action=action,
                rule_type=rule_type,
            )
            msg = "Success"
        else:
            msg = "Access Denied"

    else:
        msg = "Invalid request"

    response_data = {}
    response_data["message"] = msg
    return JsonResponse({"data": response_data})


@login_required()
def rbac_add_role_to_admin_group_ajax(request):
    """ Ajax call to add a role to an admin group

    Args:
        request(HTTPRequest): standard request

    Returns:
        HTTPResponse: success, failure or error
    """

    if request.method == "GET":
        group_id = request.GET["group_id"]
        app = request.GET["app"]
        model = request.GET["model"]
        model_id = request.GET["model_id"]

        if model_id == "None":
            model_id = None

        group = get_object_or_404(RBACAdminGroup, pk=group_id)

        if model_id:
            role_str = f"{app}.{model}.{model_id}"
        else:
            role_str = f"{app}.{model}"

        if rbac_user_is_role_admin(request.user, role_str):
            rbac_add_role_to_admin_group(
                group=group, app=app, model=model, model_id=model_id,
            )
            msg = "Success"
        else:
            msg = "Access Denied"

    else:
        msg = "Invalid request"

    response_data = {}
    response_data["message"] = msg
    return JsonResponse({"data": response_data})


@login_required()
def rbac_get_action_for_model_ajax(request):
    """ Ajax call to get the action types for a given app and model

    Args:
        request(HTTPRequest): standard request - needs to include "app" and "model"

    Returns:
        HTTPResponse: success, failure or error
    """

    if request.method == "GET":
        app = request.GET["app"]
        model = request.GET["model"]

        actions = RBACAppModelAction.objects.filter(app=app, model=model).values_list(
            "valid_action"
        )
    else:
        msg = "Invalid request"
        response_data = {}
        response_data["message"] = msg
        return JsonResponse({"data": response_data})

    html = render_to_string(
        template_name="rbac/app-model-actions.html", context={"actions": actions}
    )
    data_dict = {"data": html}
    return JsonResponse(data=data_dict, safe=False)


@login_required()
def rbac_delete_user_from_group_ajax(request):
    """ Ajax call to delete a user from a group

    Args:
        request(HTTPRequest): standard request

    Returns:
        HTTPResponse: success, failure or error
    """

    if request.method == "GET":
        member_id = request.GET["member_id"]
        group_id = request.GET["group_id"]

        member = User.objects.get(pk=member_id)
        group = RBACGroup.objects.get(pk=group_id)

        if rbac_user_is_group_admin(request.user, group):
            rbac_remove_user_from_group(member, group)
            print("User %s delete from group %s" % (member, group))
            msg = "Success"
        else:
            print("Access Denied")
            msg = "Access Denied"

    else:
        msg = "Invalid request"

    response_data = {}
    response_data["message"] = msg
    return JsonResponse({"data": response_data})


@login_required()
def rbac_delete_user_from_admin_group_ajax(request):
    """ Ajax call to delete an admin user from a group

    Args:
        request(HTTPRequest): standard request

    Returns:
        HTTPResponse: success, failure or error
    """

    if request.method == "GET":
        member_id = request.GET["member_id"]
        group_id = request.GET["group_id"]

        member = User.objects.get(pk=member_id)
        group = RBACAdminGroup.objects.get(pk=group_id)

        if rbac_user_is_admin_for_admin_group(request.user, group):
            rbac_remove_admin_user_from_group(member, group)
            msg = "Success"
        else:
            msg = "Access Denied"

    else:
        msg = "Invalid request"

    response_data = {}
    response_data["message"] = msg
    return JsonResponse({"data": response_data})


@login_required()
def rbac_delete_role_from_group_ajax(request):
    """ Ajax call to delete a role from a group

    Args:
        request(HTTPRequest): standard request

    Returns:
        HTTPResponse: success, failure or error
    """

    if request.method == "GET":
        role_id = request.GET["role_id"]

        role = RBACGroupRole.objects.get(pk=role_id)

        # must be both an admin for this group (able to edit this part of the tree)
        # and have rights to this role.

        # Use role.path not role.role (don't want action)

        role_ok = rbac_user_is_role_admin(request.user, role.path)
        group_ok = rbac_user_is_group_admin(request.user, role.group)

        print("Deleting Role")
        print(role.role)
        print(role.group)
        print(role_ok)
        print(group_ok)

        if role_ok and group_ok:

            role.delete()
            msg = "Success"
        else:
            msg = "Access Denied"

    else:
        msg = "Invalid request"

    response_data = {}
    response_data["message"] = msg
    return JsonResponse({"data": response_data})


@login_required()
def rbac_delete_role_from_admin_group_ajax(request):
    """ Ajax call to delete a role from an admin group

    Args:
        request(HTTPRequest): standard request

    Returns:
        HTTPResponse: success, failure or error
    """

    if request.method == "GET":
        role_id = request.GET["role_id"]

        role = get_object_or_404(RBACAdminGroupRole, pk=role_id)

        if role.model_id:
            role_str = f"{role.app}.{role.model}.{role.model_id}"
        else:
            role_str = f"{role.app}.{role.model}"

        if rbac_user_is_role_admin(request.user, role_str):
            role.delete()
            msg = "Success"
        else:
            msg = "Access Denied"

    else:
        msg = "Invalid request"

    response_data = {}
    response_data["message"] = msg
    return JsonResponse({"data": response_data})
