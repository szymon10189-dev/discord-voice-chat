from .presence import touch_user_activity


class PresenceActivityMiddleware:
    """Użytkownik zalogowany na dowolnej stronie = ostatnia aktywność (status online)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.pk:
            touch_user_activity(user.pk)
        return self.get_response(request)
