""" Models for Forums """
import bleach
from django.conf import settings
from django.db import models
from django.utils import timezone

from cobalt.settings import (
    BLEACH_ALLOWED_TAGS,
    BLEACH_ALLOWED_ATTRIBUTES,
    BLEACH_ALLOWED_STYLES,
)

FORUM_TYPES = [
    ("Discussion", "Discussion Forum"),
    ("Announcement", "Announcement Forum"),
    ("Club", "Club Forum"),
]


class Forum(models.Model):
    """Forum is a list of valid places to create a Post"""

    title = models.CharField("Forum Short Title", max_length=80)
    description = models.CharField("Forum Description", max_length=200)
    forum_type = models.CharField(
        "Forum Type", max_length=20, choices=FORUM_TYPES, default="Discussion"
    )
    bg_colour = models.CharField("Background Colour", max_length=20, default="white")
    fg_colour = models.CharField("Foreground Colour", max_length=20, default="black")

    def __str__(self):
        return self.title


class AbstractForum(models.Model):
    """Lots of things have the same attributes so use an Abstract Class"""

    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_date = models.DateTimeField(default=timezone.now)
    last_change_date = models.DateTimeField(null=True, blank=True)
    last_changed_by = models.CharField(
        "Last Changed By", max_length=50, null=True, blank=True
    )

    class Meta:
        """We are abstract"""

        abstract = True
        ordering = ["-created_date"]


class Post(AbstractForum):
    """A Post is the highest level thing in Forums"""

    forum = models.ForeignKey(Forum, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    text = models.TextField()
    comment_count = models.IntegerField(default=0)

    def __str__(self):
        return self.title

    # If the text changes, run it through bleach before saving
    def save(self, *args, **kwargs):
        if getattr(self, "_text_changed", True):
            self.text = bleach.clean(
                self.text,
                strip=True,
                tags=BLEACH_ALLOWED_TAGS,
                attributes=BLEACH_ALLOWED_ATTRIBUTES,
                styles=BLEACH_ALLOWED_STYLES,
            )
        super(Post, self).save(*args, **kwargs)


class Comment1(AbstractForum):
    """First level comments"""

    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    text = models.TextField()
    comment1_count = models.IntegerField(default=0)

    def __str__(self):
        return "%s - comment by %s" % (self.post.title, self.author.full_name)


class Comment2(AbstractForum):
    """Second level comments"""

    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    comment1 = models.ForeignKey(Comment1, on_delete=models.CASCADE)
    text = models.TextField()


class AbstractLike(models.Model):
    """Abstract for likes"""

    liker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        """We are abstract"""

        abstract = True


class LikePost(AbstractLike):
    """Like for a post"""

    post = models.ForeignKey(Post, on_delete=models.CASCADE)


class LikeComment1(AbstractLike):
    """Like for a comment1"""

    comment1 = models.ForeignKey(Comment1, on_delete=models.CASCADE)


class LikeComment2(AbstractLike):
    """Like for a comment2"""

    comment2 = models.ForeignKey(Comment2, on_delete=models.CASCADE)


class ForumFollow(models.Model):
    """List of Forums that a user is subscribed to"""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    forum = models.ForeignKey(Forum, on_delete=models.CASCADE)

    def __str__(self):
        return "%s-%s" % (self.user, self.forum)
