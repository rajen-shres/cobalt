import re
from urllib.error import HTTPError
from urllib.request import urlopen

from django.shortcuts import render

from cobalt.settings import COBALT_HOSTNAME
from events.models import Congress
from rbac.decorators import rbac_check_role
from utils.models import Slug


def check_slug_is_free(slug):
    """Check if a slug is in use or not"""

    return not Slug.objects.filter(slug=slug).exists()


def create_new_slug(slug, redirect_path, owner):
    """create a slug if it doesn't already exist"""

    if Slug.objects.filter(slug=slug).exists():
        return False

    Slug(slug=slug, redirect_path=redirect_path, owner=owner).save()
    return True


def validate_cobalt_slug(slug_text, redirect_path):
    """validate the slug text and the path.

    Returns:
        valid: boolean
        message: str

    """

    # Check path
    if redirect_path.find("/") == 0:
        return (
            False,
            "Link cannot start with a backslash.",
        )

    # Check if slug already exists
    slug = Slug.objects.filter(slug=slug_text).first()
    if slug:
        return False, "Short name already used"

    # check link
    if redirect_path:
        # Special case for congresses which may not be published yet
        match = re.search(r"events/congress/view/(\d+)", redirect_path)
        if match:
            if Congress.objects.filter(pk=match[1]).exists():
                slug_msg = "Name is available and link is valid."
                show_save = True
            else:
                slug_msg = "Name is available, but link is invalid."
                show_save = False
        else:
            # Try url to see if valid
            url = f"http://{COBALT_HOSTNAME}/{redirect_path}"

            try:
                urlopen(url)
                slug_msg = "Name is available and link is valid."
                show_save = True

            except HTTPError:
                slug_msg = "Name is available, but link is invalid."
                show_save = False

    else:
        slug_msg = "Name is available but link is missing."
        show_save = False

    return show_save, slug_msg


@rbac_check_role("notifications.admin.view")
def admin_manage_slugs(request):
    """Admin view of all slugs"""

    slugs = Slug.objects.all().order_by("slug")

    return render(request, "utils/admin_manage_slugs.html", {"slugs": slugs})
