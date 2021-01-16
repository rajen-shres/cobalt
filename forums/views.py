""" Views for Forums """
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone
from django.template.loader import render_to_string
from django.urls import reverse
from django.contrib import messages
from django.db import transaction
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from rbac.core import (
    rbac_user_blocked_for_model,
    rbac_user_has_role,
    rbac_get_users_in_group,
    rbac_add_user_to_group,
    rbac_get_users_with_role,
)
from cobalt.settings import COBALT_HOSTNAME
from notifications.views import contact_member
from rbac.models import RBACGroup, RBACGroupRole, RBACUserGroup
from notifications.views import (
    notify_happening,
    add_listener,
    remove_listener,
    check_listener,
)
from utils.utils import cobalt_paginator
from rbac.views import rbac_forbidden
from .forms import PostForm, CommentForm, Comment2Form, ForumForm
from .filters import PostFilter
from .models import (
    Post,
    Comment1,
    Comment2,
    LikePost,
    LikeComment1,
    LikeComment2,
    Forum,
    ForumFollow,
)
from accounts.models import User
import json


@login_required()
def post_list_single_forum(request, forum_id):
    """shows posts for a single forum

    Args:
        request(HTTPRequest): standard user request
        forum_id(int): forum to view

    Returns:
        page(HTTPResponse): page with list of posts
    """

    forum = get_object_or_404(Forum, pk=forum_id)

    # check access
    blocked = rbac_user_blocked_for_model(
        user=request.user, app="forums", model="forum", action="view"
    )
    if forum_id in blocked:
        return rbac_forbidden(request, "forums.forum.%s.view" % forum_id)

    posts_list = Post.objects.filter(forum=forum).order_by("-created_date")

    # handle pagination
    posts = cobalt_paginator(request, posts_list, 30)

    can_post = rbac_user_has_role(request.user, f"forums.forum.{forum_id}.create")

    return render(
        request,
        "forums/post_list_short.html",
        {"things": posts, "forum": forum, "can_post": can_post},
    )


@login_required()
@transaction.atomic
def post_detail(request, pk):
    """Main view for existing post.

    Shows post and existing comments and allows the user to coment at either
    level (Comment1 or Comment2).

    Args:
        request(HTTPRequest): standard request object
        pk(int):    primary key of post

    Returns:
        HTTPResponse
    """

    # Check access
    post = get_object_or_404(Post, pk=pk)
    role = "forums.forum.%s.view" % post.forum.id
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if request.method == "POST":

        # Check user permissions to post
        role = "forums.forum.%s.create" % post.forum.id
        if not rbac_user_has_role(request.user, role):
            return rbac_forbidden(request, role)

        # identify which form submitted this - comments1 or comments2
        if "submit-c1" in request.POST:
            form = CommentForm(request.POST)
        elif "submit-c2" in request.POST:
            form = Comment2Form(request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()
            # update count on parent
            post.post.comment_count += 1
            post.post.save()
            # if this is a c2 then update count on c1
            if "submit-c2" in request.POST:
                post.comment1.comment1_count += 1
                post.comment1.save()

            # Tell people
            base_link = reverse("forums:post_detail", args=[post.post.id])
            host = request.get_host()

            if "submit-c1" in request.POST:
                link = f"{base_link}#target_{post.id}"
            else:
                link = f"{base_link}#target_{post.comment1.id}_{post.id}"

            text_html = post.text.replace("\r", "<br>")

            email_body = "%s commented on %s in Forum: '%s.'<br><br>%s" % (
                request.user,
                post.post.title,
                post.post.forum,
                text_html,
            )

            context = {
                "name": "[NAME]",
                "title": "New Comment on: %s" % post.post.title,
                "email_body": email_body,
                "link": link,
                "host": host,
                "link_text": "Go To Reply",
            }

            html_msg = render_to_string(
                "notifications/email_with_button.html", context
            )

            msg = "New Comment by %s on %s" % (request.user, post.post.title)

            email_subject = "New Comment on Post: %s" % post.post.title

            # call notifications
            notify_happening(
                application_name="Forums",
                event_type="forums.post.comment",
                msg=msg,
                html_msg=html_msg,
                topic=post.post.id,
                link=link,
                email_subject=email_subject,
                user=request.user,
            )

        else:
            print(form.errors)
    form = CommentForm()
    form2 = Comment2Form()
    post = get_object_or_404(Post, pk=pk)
    post_likes = LikePost.objects.filter(post=post)
    comments1 = Comment1.objects.filter(post=post).order_by("pk")

    # TODO: Now that we have counters for comments at the Post and Comment1 level
    # this code could potentially be made more efficient.

    total_comments = 0
    comments1_new = []  # comments1 is immutable - make a copy
    for c1 in comments1:
        # add related c2 objects to c1
        c2 = Comment2.objects.filter(comment1=c1).order_by("pk")
        c2_new = []
        for i in c2:
            i.c2_likes = LikeComment2.objects.filter(comment2=i).count()
            c2_new.append(i)
        c1.c2 = c2_new
        # number of comments
        total_comments += 1
        total_comments += len(c1.c2)
        # number of likes
        c1.c1_likes = LikeComment1.objects.filter(comment1=c1).count()
        comments1_new.append(c1)

    following = check_listener(
        member=request.user,
        application="Forums",
        event_type="forums.post.comment",
        topic=pk,
    )

    is_moderator = rbac_user_has_role(
        request.user, "forums.moderate.%s.edit" % post.forum.id
    )

    return render(
        request,
        "forums/post_detail.html",
        {
            "form": form,
            "form2": form2,
            "post": post,
            "comments1": comments1_new,
            "post_likes": post_likes,
            "total_comments": total_comments,
            "following": following,
            "is_moderator": is_moderator,
        },
    )


@login_required()
@transaction.atomic
def post_new(request, forum_id=None):
    """ Create a new post in a forum """

    if request.method == "POST":
        form = PostForm(request.POST)
        if form.is_valid():
            # check access
            role = "forums.forum.%s.create" % form.cleaned_data["forum"].id
            if not rbac_user_has_role(request.user, role):
                return rbac_forbidden(request, role)

            post = form.save(commit=False)
            post.author = request.user
            post.published_date = timezone.now()

            # Summernote allows images to overflow their divs - we don't want that
            text = post.text

            # We are looking to turn ....<img..>... into
            # ...<div style="overflow:hidden;"><img...></div>

            loc = text.find("<img")
            while loc >= 0:
                beginning = text[:loc]
                ending = text[loc:]
                endloc = ending.find(">") + 1
                new_ending = "%s</div>%s" % (ending[:endloc], ending[endloc:])
                text = "%s<div style='overflow:hidden;'>%s" % (beginning, new_ending)

                # find next, string is now longer
                loc = text.find("<img", loc + 36)

            post.text = text

            post.save()

            notify_me = form.cleaned_data['get_notified_of_replies']
            if notify_me == "True":
                add_listener(
                    member=request.user,
                    application="Forums",
                    event_type="forums.post.comment",
                    topic=post.id,
                )

            messages.success(
                request, "Post created", extra_tags="cobalt-message-success"
            )

            link = reverse("forums:post_detail", args=[post.id])
            host = request.get_host()
            absolute_link = "http://%s%s" % (host, link)

            email_body = "%s created a new post in %s called '%s.'" % (
                post.author,
                post.forum.title,
                post.title,
            )

            context = {
                "name": request.user.first_name,
                "title": "New Post: %s" % post.title,
                "email_body": email_body,
                "absolute_link": absolute_link,
                "host": host,
                "link_text": "See Post",
            }

            html_msg = render_to_string(
                "notifications/email-notification.html", context
            )

            msg = "New Post %s by %s" % (post.title, post.author)

            email_subject = "New Post in Forum: %s" % post.forum.title

            # Tell people
            notify_happening(
                application_name="Forums",
                event_type="forums.post.create",
                msg=msg,
                html_msg=html_msg,
                topic=post.forum.id,
                link=link,
                email_subject=email_subject,
                user=request.user,
            )

            return redirect("forums:post_detail", pk=post.pk)

    # If we got here then either it is not a post, or it is with an invalid form

    # see which forums are blocked for this user - load a list of the others
    blocked_forums = rbac_user_blocked_for_model(
        user=request.user, app="forums", model="forum", action="create"
    )
    valid_forums = Forum.objects.exclude(id__in=blocked_forums)

    if request.method == "POST":  # invalid form
        form = PostForm(request.POST, valid_forums=valid_forums)
    else:  # blank form
        form = PostForm(valid_forums=valid_forums)

    if forum_id:
        form.fields["forum"].initial = forum_id
        forum = get_object_or_404(Forum, pk=forum_id)
    else:
        forum = None

    return render(request, "forums/post_edit.html", {"form": form, "forum": forum})


@login_required()
@transaction.atomic
def post_edit(request, post_id):
    """Edit a post in a forum.

    This can be done by the user who created it or a moderator"""

    post = get_object_or_404(Post, pk=post_id)
    role = "forums.forum.%s.create" % post.forum.id

    # check access
    if not (
        (rbac_user_has_role(request.user, role) and post.author == request.user)
        or rbac_user_has_role(request.user, "forums.moderate.%s.edit" % post.forum.id)
    ):

        return rbac_forbidden(request, role)

    else:

        if request.method == "POST":
            if "publish" in request.POST:  # Publish
                form = PostForm(request.POST, instance=post)
                if form.is_valid():

                    post = form.save(commit=False)
                    post.last_change_date = timezone.now()
                    post.save()
                    messages.success(
                        request, "Post edited", extra_tags="cobalt-message-success"
                    )
                    return redirect("forums:post_detail", pk=post.pk)

            elif "delete" in request.POST:  # Delete
                post.delete()
                messages.success(
                    request, "Post deleted", extra_tags="cobalt-message-success"
                )
                return redirect("forums:forums")

            else:  # Maybe cancel hit or back button - reload page
                return redirect("forums:post_edit", post_id=post_id)

        # see which forums are blocked for this user - load a list of the others
        blocked_forums = rbac_user_blocked_for_model(
            user=request.user, app="forums", model="forum", action="create"
        )
        valid_forums = Forum.objects.exclude(id__in=blocked_forums)
        form = PostForm(valid_forums=valid_forums, instance=post)

    return render(
        request,
        "forums/post_edit.html",
        {"form": form, "request": request, "edit": True, "forum": post.forum},
    )


@login_required()
def like_post(request, pk):
    """Function to like a post over ajax

    Args:
        request(HTTPRequest): standard request object
        pk(int):    Primary key of the post to like

    Returns:
        HttpResponse
    """

    if request.method == "POST":
        already_liked = LikePost.objects.filter(post=pk, liker=request.user)
        if not already_liked:
            like = LikePost()
            like.liker = request.user
            like.post = Post.objects.get(pk=pk)
            like.save()
            return HttpResponse("ok")
        else:
            return HttpResponse("already liked")
    return HttpResponse("Invalid request")


@login_required()
def like_comment1(request, pk):
    """Function to like a comment1 over ajax

    Args:
        request(HTTPRequest): standard request object
        pk(int):    Primary key of the comment1 to like

    Returns:
        HttpResponse
    """
    if request.method == "POST":
        already_liked = LikeComment1.objects.filter(comment1=pk, liker=request.user)
        if not already_liked:
            like = LikeComment1()
            like.liker = request.user
            like.comment1 = Comment1.objects.get(pk=pk)
            like.save()
            return HttpResponse("ok")
        else:
            return HttpResponse("already liked")
    return HttpResponse("Invalid request")


@login_required()
def like_comment2(request, pk):
    """Function to like a comment2 over ajax

    Args:
        request(HTTPRequest): standard request object
        pk(int):    Primary key of the comment2 to like

    Returns:
        HttpResponse
    """

    if request.method == "POST":
        already_liked = LikeComment2.objects.filter(comment2=pk, liker=request.user)
        if not already_liked:
            like = LikeComment2()
            like.liker = request.user
            like.comment2 = Comment2.objects.get(pk=pk)
            like.save()
            return HttpResponse("ok")
        else:
            return HttpResponse("already liked")
    return HttpResponse("Invalid request")


@login_required
def forum_list(request):
    """View to show a list of all forums

    Args:
        request(HTTPRequest): standard request object

    Returns:
        HTTPResponse
    """

    # get allowed forum list
    blocked_forums = rbac_user_blocked_for_model(
        user=request.user, app="forums", model="forum", action="view"
    )
    forums = Forum.objects.exclude(id__in=blocked_forums)

    forums_all = []

    forum_follows = list(
        ForumFollow.objects.filter(user=request.user).values_list("forum", flat=True)
    )

    # TODO: remove redundant fields in this bit
    for forum in forums:
        detail = {}
        count = Post.objects.filter(forum=forum).count()
        if count != 0:
            latest_post = Post.objects.filter(forum=forum).latest("created_date")
            latest_author = latest_post.author
            latest_title = latest_post.title
            latest_date = latest_post.created_date
        else:
            latest_author = ""
            latest_title = "No posts yet"
            latest_date = ""

        detail["id"] = forum.id
        detail["title"] = forum.title
        detail["description"] = forum.description
        detail["count"] = count
        detail["latest_author"] = latest_author
        detail["latest_title"] = latest_title
        detail["latest_date"] = latest_date
        detail["forum_type"] = forum.forum_type
        if forum.id in forum_follows:
            detail["follows"] = True
        else:
            detail["follows"] = False

        forums_all.append(detail)

    if rbac_user_has_role(request.user, "forums.admin.edit"):
        is_admin = True
    else:
        is_admin = False

    print(is_admin)

    return render(
        request, "forums/forum_list.html", {"forums": forums_all, "is_admin": is_admin}
    )


@login_required
def post_search(request):
    post_list = Post.objects.all()
    post_filter = PostFilter(request.GET, queryset=post_list)

    filtered_qs = post_filter.qs

    paginator = Paginator(filtered_qs, 10)

    page = request.GET.get("page")
    try:
        response = paginator.page(page)
    except PageNotAnInteger:
        response = paginator.page(1)
    except EmptyPage:
        response = paginator.page(paginator.num_pages)

    user = request.GET.get("author")
    title = request.GET.get("title")
    forum = request.GET.get("forum")
    searchparams = "author=%s&title=%s&forum=%s&" % (user, title, forum)

    return render(
        request,
        "forums/post_search.html",
        {"filter": post_filter, "things": response, "searchparams": searchparams},
    )


@login_required()
def follow_forum_ajax(request, forum_id):
    """Function to follow a forum over ajax

    Args:
        request(HTTPRequest): standard request object
        pk(int):    Primary key of the forum to follow

    Returns:
        HttpResponse
    """

    forum = get_object_or_404(Forum, pk=forum_id)
    if ForumFollow.objects.filter(forum=forum, user=request.user).count() == 0:
        follow = ForumFollow(forum=forum, user=request.user)
        follow.save()
        return HttpResponse("ok")
    else:
        return HttpResponse("already following")
    return HttpResponse("Invalid request")


@login_required()
def unfollow_forum_ajax(request, forum_id):
    """Function to unfollow a forum over ajax

    Args:
        request(HTTPRequest): standard request object
        pk(int):    Primary key of the forum to unfollow

    Returns:
        HttpResponse
    """

    forum = get_object_or_404(Forum, pk=forum_id)
    follow = ForumFollow.objects.filter(forum=forum, user=request.user)
    follow.delete()
    return HttpResponse("ok")


@login_required()
def follow_post_ajax(request, post_id):
    """Function to follow a post over ajax

    Args:
        request(HTTPRequest): standard request object
        post_id(int):    Primary key of the post to follow

    Returns:
        HttpResponse
    """

    add_listener(
        member=request.user,
        application="Forums",
        event_type="forums.post.comment",
        topic=post_id,
    )
    return HttpResponse("You will receive an email when someone comments on this post.")


@login_required()
def unfollow_post_ajax(request, post_id):
    """Function to unfollow a post over ajax

    Args:
        request(HTTPRequest): standard request object
        post_id(int):    Primary key of the post to unfollow

    Returns:
        HttpResponse
    """

    remove_listener(
        member=request.user,
        application="Forums",
        event_type="forums.post.comment",
        topic=post_id,
    )
    return HttpResponse("You will no longer receive email notifications for this post.")


@login_required()
def forum_create(request):
    """view to create a new forum

    Args: request(HTTPRequest): standard request object

    Returns:
        HttpResponse
    """

    role = "forums.admin.edit"
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    if request.method == "POST":
        form = ForumForm(request.POST)
        if form.is_valid():
            forum = Forum()
            forum.title = form.cleaned_data["title"]
            forum.description = form.cleaned_data["description"]
            forum.save()
            messages.success(
                request, "Forum created", extra_tags="cobalt-message-success"
            )
            return redirect("forums:post_list_single_forum", forum_id=forum.id)
        else:
            print(form.errors)
    else:
        form = ForumForm()

    return render(
        request, "forums/forum_edit.html", {"form": form, "title": "Create New Forum"}
    )


@login_required()
def forum_delete_ajax(request, forum_id):
    """Function to delete a forum

    Args:
        request(HTTPRequest): standard request object
        forum_id(int):    Primary key of the forum

    Returns:
        HttpResponse
    """

    # check access
    role = "forums.admin.edit"
    if not rbac_user_has_role(request.user, role):
        return rbac_forbidden(request, role)

    forum = get_object_or_404(Forum, pk=forum_id)
    forum.delete()

    return HttpResponse("%s deleted." % forum)


@login_required()
def comment_edit_common(request, comment, comment_type):
    """ common code for editing c1 and c2 """

    role = "forums.forum.%s.create" % comment.post.forum.id

    is_moderator = rbac_user_has_role(
        request.user, "forums.moderate.%s.edit" % comment.post.forum.id
    )

    # check access
    if not (
        (rbac_user_has_role(request.user, role) and comment.author == request.user)
        or is_moderator
    ):
        return rbac_forbidden(request, role)

    else:
        # access is okay
        if request.method == "POST":
            form = CommentForm(request.POST, instance=comment)
            if form.is_valid():

                comment = form.save(commit=False)
                comment.last_change_date = timezone.now()

                # Mark as edited by moderator unless own comment
                if is_moderator and comment.author != request.user:
                    comment.last_changed_by = "Moderator"
                else:
                    comment.last_changed_by = request.user.first_name
                comment.save()
                messages.success(
                    request, "Comment edited", extra_tags="cobalt-message-success"
                )
                if comment_type == "c1":
                    target = f"#target_{comment.id}"
                elif comment_type == "c2":
                    target = f"#target_{comment.comment1.id}_{comment.id}"

                url = (
                    reverse("forums:post_detail", kwargs={"pk": comment.post.pk})
                    + target
                )
                return redirect(url)

            else:
                print(form.errors)

        form = CommentForm(instance=comment)

    return render(
        request,
        "forums/comment_edit.html",
        {"form": form, "post": comment.post.id},
    )


@login_required()
def comment1_edit(request, comment_id):

    comment = get_object_or_404(Comment1, pk=comment_id)
    return comment_edit_common(request, comment, "c1")


@login_required()
def comment2_edit(request, comment_id):

    comment = get_object_or_404(Comment2, pk=comment_id)
    return comment_edit_common(request, comment, "c2")


@login_required()
def forum_edit(request, forum_id):
    """ View to allow an admin to edit a forums settings """

    # Moderators or forum admins can do this
    if not (
        rbac_user_has_role(request.user, "forums.admin.edit")
        or rbac_user_has_role(request.user, f"forums.moderate.{forum_id}.edit")
    ):
        return rbac_forbidden(request, f"forums.moderate.{forum_id}.edit")

    forum = get_object_or_404(Forum, pk=forum_id)

    if request.method == "POST":
        form = ForumForm(request.POST, instance=forum)
        if form.is_valid():
            forum.title = form.cleaned_data["title"]
            forum.description = form.cleaned_data["description"]
            forum.save()
            messages.success(
                request, "Forum edited", extra_tags="cobalt-message-success"
            )
            return redirect("forums:post_list_single_forum", forum_id=forum.id)
        else:
            print(form.errors)
    else:
        form = ForumForm(instance=forum)

    blocked_users = rbac_get_users_in_group(f"forums.forum.{forum_id}.blocked_users")

    return render(
        request,
        "forums/forum_edit.html",
        {
            "form": form,
            "title": "Edit Forum",
            "blocked_users": blocked_users,
            "forum": forum,
        },
    )


@login_required()
def block_user(request, user_id, forum_id):
    """ stop a user from being able to post to a forum """

    if not (
        rbac_user_has_role(request.user, "forums.admin.edit")
        or rbac_user_has_role(request.user, f"forums.moderate.{forum_id}.edit")
    ):
        return rbac_forbidden(request, f"forums.moderate.{forum_id}.edit")

    user = get_object_or_404(User, pk=user_id)
    forum = get_object_or_404(Forum, pk=forum_id)
    group = RBACGroup.objects.filter(
        name_qualifier=f"forums.forum.{forum_id}", name_item="blocked_users"
    ).first()

    # If group exists do not change its permissions

    if not group:
        group = RBACGroup(
            name_qualifier=f"forums.forum.{forum_id}",
            name_item="blocked_users",
            description=f"Auto generated - block users from forum {forum_id}",
        )
        group.save()

        role = RBACGroupRole(
            group=group,
            app="forums",
            model="forum",
            model_id=forum_id,
            action="create",
            rule_type="Block",
        )
        role.save()

    rbac_add_user_to_group(user, group)

    messages.success(
        request,
        f"{user} blocked from posting in forum - {forum}",
        extra_tags="cobalt-message-success",
    )
    return redirect("forums:post_list_single_forum", forum_id=forum.id)


@login_required()
def unblock_user(request, user_id, forum_id):
    """ remove block on a user so they can post to a forum """

    if not (
        rbac_user_has_role(request.user, "forums.admin.edit")
        or rbac_user_has_role(request.user, f"forums.moderate.{forum_id}.edit")
    ):
        return rbac_forbidden(request, f"forums.moderate.{forum_id}.edit")

    user = get_object_or_404(User, pk=user_id)
    forum = get_object_or_404(Forum, pk=forum_id)
    group = RBACGroup.objects.filter(
        name_qualifier=f"forums.forum.{forum_id}", name_item="blocked_users"
    ).first()
    blocked = RBACUserGroup.objects.filter(member=user, group=group).first()
    blocked.delete()

    messages.success(
        request,
        f"{user} can now post in forum - {forum}",
        extra_tags="cobalt-message-success",
    )
    return redirect("forums:forum_edit", forum_id=forum.id)


@login_required()
def report_abuse(request):
    """ Ajax call to report a post or comment that someone doesn't like """

    if request.method == "POST":
        data = json.loads(request.body.decode("utf-8"))
        text_type = data["text_type"]
        id = int(data["id"])
        reason = data["reason"]

        # Handle the different types of objects
        if text_type == "Post":
            post = get_object_or_404(Post, pk=id)
            c1 = None
            c2 = None
            author = post.author

        elif text_type == "C1":
            c1 = get_object_or_404(Comment1, pk=id)
            post = c1.post
            c2 = None
            author = c1.author

        elif text_type == "C2":
            c2 = get_object_or_404(Comment2, pk=id)
            c1 = c2.comment1
            post = c1.post
            author = c2.author

        notify_moderators_of_abuse(post, c1, c2, request.user, author, reason)

        response_data = {}
        response_data["message"] = "Success"
        return JsonResponse({"data": response_data})


def notify_moderators_of_abuse(post, c1, c2, user, author, reason):
    """ Let moderators know about a complaint """

    moderators = rbac_get_users_with_role("forums.moderate.%s.edit" % post.forum.id)

    link = reverse("forums:post_detail", kwargs={"pk": post.id})

    email_body = f"""<h3>Forum: {post.forum}</h3>
                      <h3>Reason: {reason}</h3>
                      <h3>Post: {post.title}</h3>
                    <br><br>

                   """

    if c2:
        email_body += c2.text
        link += f"#target_{c1.id}_{c2.id}"
    elif c1:
        email_body += c1.text
        link += f"#target_{c1.id}"
    else:
        email_body += post.text

    email_body += "<br><br>"

    for moderator in moderators:

        context = {
            "name": moderator.first_name,
            "title": f"Report on {author.full_name} by {user.full_name}",
            "email_body": email_body,
            "host": COBALT_HOSTNAME,
            "link": link,
            "link_text": "View Post",
        }

        html_msg = render_to_string("notifications/email_with_button.html", context)

        # send
        contact_member(
            member=moderator,
            msg=f"Report on {author.full_name} by {user.full_name}",
            contact_type="Email",
            html_msg=html_msg,
            link=link,
            subject=f"Report on {author.full_name} by {user.full_name}",
        )


def forums_status_summary():
    """ Used by utils status to check on the health of forums """

    latest_post = Post.objects.all().order_by("-created_date").first()
    latest_c1 = Comment1.objects.all().order_by("-created_date").first()
    latest_c2 = Comment2.objects.all().order_by("-created_date").first()

    return {"latest_post": latest_post, "latest_c1": latest_c1, "latest_c2": latest_c2}
