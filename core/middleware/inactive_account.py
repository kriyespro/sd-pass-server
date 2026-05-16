"""Log out deactivated users and send them to the login page."""
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect


class InactiveAccountMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and not user.is_active:
            logout(request)
            messages.error(
                request,
                'Your account has been deactivated. Contact your administrator for help.',
            )
            return redirect('accounts:login')
        return self.get_response(request)
