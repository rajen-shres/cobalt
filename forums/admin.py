from django.contrib import admin
from django_summernote.admin import SummernoteModelAdmin
from .models import (
    Forum,
    Post,
    Comment1,
    Comment2,
    LikePost,
    LikeComment1,
    LikeComment2,
    ForumFollow,
)


# class PostAdmin(SummernoteModelAdmin):
#     summernote_fields = ("text",)


# admin.site.register(Post, PostAdmin)
admin.site.register(Post)
admin.site.register(Forum)
admin.site.register(Comment1)
admin.site.register(Comment2)
admin.site.register(LikePost)
admin.site.register(LikeComment1)
admin.site.register(LikeComment2)
admin.site.register(ForumFollow)
