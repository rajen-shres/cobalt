from accounts.models import User
from django.utils import timezone


class CobaltMiddleware(object):
    """ custom middleware to add last activity time to user object.

        If you are here to switch this off to improve performance then
        I apologise. It seemed like a good idea at the time!

    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_anonymous:
            request.user.last_activity = timezone.now()
            request.user.save()
        return None
