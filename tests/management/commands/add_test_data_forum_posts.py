""" Script to create cobalt test data """
from django.core.exceptions import SuspiciousOperation

from cobalt.settings import (
    RBAC_EVERYONE,
    TIME_ZONE,
    DUMMY_DATA_COUNT,
    TBA_PLAYER,
    COBALT_HOSTNAME,
    ALL_SYSTEM_ACCOUNTS,
)
from accounts.models import User
from django.core.management.base import BaseCommand
from accounts.management.commands.accounts_core import create_fake_user
from forums.models import (
    Post,
    Comment1,
    Comment2,
    LikePost,
    LikeComment1,
    LikeComment2,
    Forum,
)
import random
from essential_generators import DocumentGenerator
import datetime
import pytz
from django.utils.timezone import make_aware, now
import glob
import sys
from inspect import currentframe, getframeinfo
from importlib import import_module

TZ = pytz.timezone(TIME_ZONE)
DATA_DIR = "tests/test_data"


class Command(BaseCommand):
    def __init__(self):
        super().__init__()
        self.gen = DocumentGenerator()
        self.id_array = {}

    def add_comments(self, post, user_list):
        """add comments to a forum post"""

        liker_list = list(set(user_list) - {post.author})
        sample_size = random.randrange(int(len(liker_list) * 0.8))
        for liker in random.sample(liker_list, sample_size):
            like = LikePost(post=post, liker=liker)
            like.save()
        for _ in range(random.randrange(10)):
            text = self.random_paragraphs()
            c1 = Comment1(post=post, text=text, author=random.choice(user_list))
            c1.save()
            liker_list = list(set(user_list) - {c1.author})
            sample_size = random.randrange(int(len(liker_list) * 0.8))
            for liker in random.sample(liker_list, sample_size):
                like = LikeComment1(comment1=c1, liker=liker)
                like.save()
            post.comment_count += 1
            post.save()
            for _ in range(random.randrange(10)):
                text = self.random_paragraphs()
                c2 = Comment2(
                    post=post, comment1=c1, text=text, author=random.choice(user_list)
                )
                c2.save()
                post.comment_count += 1
                post.save()
                c1.comment1_count += 1
                c1.save()
                liker_list = list(set(user_list) - {c2.author})
                sample_size = random.randrange(int(len(liker_list) * 0.8))
                for liker in random.sample(liker_list, sample_size):
                    like = LikeComment2(comment2=c2, liker=liker)
                    like.save()

    def random_paragraphs(self):
        """generate a random paragraph"""
        text = self.gen.paragraph()
        for _ in range(random.randrange(10)):
            text += "\n\n" + self.gen.paragraph()
        return text

    def random_sentence(self):
        """generate a random sentence"""
        return self.gen.sentence()

    def random_paragraphs_with_stuff(self):
        """generate a more realistic rich test paragraph with headings and pics"""

        sizes = [
            ("400x500", "400px"),
            ("400x300", "400px"),
            ("700x300", "700px"),
            ("900x500", "900px"),
            ("200x200", "200px"),
            ("800x200", "800px"),
            ("500x400", "500px"),
        ]

        text = self.gen.paragraph()
        for _ in range(random.randrange(10)):
            type = random.randrange(8)
            if type == 5:  # no good reason
                text += f"<h2>{self.gen.sentence()}</h2>"
            elif type == 7:
                index = random.randrange(len(sizes))
                text += (
                    "<p><img src='https://source.unsplash.com/random/%s' style='width: %s;'><br></p>"
                    % (sizes[index][0], sizes[index][1])
                )
            else:
                text += f"<p>{self.gen.paragraph()}</p>"
        return text

    def handle(self, *args, **options):
        if COBALT_HOSTNAME in ["myabf.com.au", "www.myabf.com.au"]:
            raise SuspiciousOperation(
                "Not for use in production. This cannot be used in a production system."
            )

        print("Running add_rbac_test_data_forum_posts")

        try:
            # create dummy Posts
            print("\nCreating dummy forum posts")
            print("Running", end="", flush=True)
            for count, _ in enumerate(range(DUMMY_DATA_COUNT * 10), start=1):

                user_list = User.objects.exclude(id__in=ALL_SYSTEM_ACCOUNTS)
                forums = Forum.objects.all()

                post = Post(
                    forum=random.choice(forums),
                    title=self.random_sentence(),
                    text=self.random_paragraphs_with_stuff(),
                    author=random.choice(user_list),
                )
                post.save()
                print(".", end="", flush=True)
                self.add_comments(post, user_list)
                if count % 100 == 0:
                    print(count, flush=True)
            print("\n")

        except KeyboardInterrupt:
            print("\n\nTest data loading interrupted by user\n")
            sys.exit(0)
