from django.urls import path
from . import views

app_name = "forums"  # pylint: disable=invalid-name

urlpatterns = [
    path("", views.forum_list, name="forums"),
    # path("post/list/", views.post_list_filter, name="post_list_filter"),
    path("post/<int:pk>/", views.post_detail, name="post_detail"),
    # path(
    #     "forum-colours/<int:forum_id>",
    #     views.forum_colours_ajax,
    #     name="forum_colours_ajax",
    # ),
    path(
        "forum/list/<int:forum_id>/",
        views.post_list_single_forum,
        name="post_list_single_forum",
    ),
    path("post/new/", views.post_new, name="post_new"),
    path("post/new/<int:forum_id>", views.post_new, name="post_new_with_id"),
    path("comment1/edit/<int:comment_id>", views.comment1_edit, name="comment1_edit"),
    path("comment2/edit/<int:comment_id>", views.comment2_edit, name="comment2_edit"),
    path("post/search/", views.post_search, name="post_search"),
    path("post/edit/<int:post_id>", views.post_edit, name="post_edit"),
    path("forum/list", views.forum_list, name="forum_list"),
    path("forum/create", views.forum_create, name="forum_create"),
    path("forum/report-abuse", views.report_abuse, name="report_abuse"),
    path("forum/edit/<int:forum_id>", views.forum_edit, name="forum_edit"),
    path("forum/delete/<int:forum_id>", views.forum_delete_ajax, name="forum_delete"),
    path("post/like-post/<int:pk>/", views.like_post, name="like_post"),
    path(
        "forum/blockuser/<int:user_id>/<int:forum_id>",
        views.block_user,
        name="block_user",
    ),
    path(
        "forum/unblockuser/<int:user_id>/<int:forum_id>",
        views.unblock_user,
        name="unblock_user",
    ),
    path("post/like-comment1/<int:pk>/", views.like_comment1, name="like_comment1"),
    path("post/like-comment2/<int:pk>/", views.like_comment2, name="like_comment2"),
    path(
        "forum/follow/<int:forum_id>/",
        views.follow_forum_ajax,
        name="follow_forum_ajax",
    ),
    path(
        "forum/unfollow/<int:forum_id>/",
        views.unfollow_forum_ajax,
        name="unfollow_forum_ajax",
    ),
    path(
        "post/follow/<int:post_id>/", views.follow_post_ajax, name="follow_post_ajax",
    ),
    path(
        "post/unfollow/<int:post_id>/",
        views.unfollow_post_ajax,
        name="unfollow_post_ajax",
    ),
]
