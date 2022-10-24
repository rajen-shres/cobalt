from utils.models import Slug


def check_slug_is_free(slug):
    """Check if a slug is in use or not"""

    return not Slug.objects.filter(slug=slug).exists()


def create_new_slug(slug, redirect_path):
    """create a slug if it doesn't already exist"""

    if Slug.objects.filter(slug=slug).exists():
        return False

    Slug(slug=slug, redirect_path=redirect_path).save()
    return True
