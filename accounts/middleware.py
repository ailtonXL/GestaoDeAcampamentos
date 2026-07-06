from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and getattr(user, 'must_change_password', False):
            allowed_paths = {
                reverse('password_change'),
                reverse('password_change_done'),
                reverse('logout'),
            }
            if request.path not in allowed_paths and not request.path.startswith('/static/'):
                return redirect('password_change')

        return self.get_response(request)
