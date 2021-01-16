""" Management Commands for forums """
from forums.models import Forum


def create_forum(self, title, description, forum_type):
    forum = Forum.objects.filter(title=title).first()
    if forum:
        self.stdout.write(self.style.SUCCESS("%s forum already exists - ok" % title))
    else:
        forum = Forum(title=title, description=description)
        forum.forum_type = forum_type
        forum.save()
        self.stdout.write(
            self.style.SUCCESS("Successfully created new forum - %s" % title)
        )
    return forum
