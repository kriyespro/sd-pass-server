from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from apps.billing.services import get_or_create_subscription


class AccountAdapter(DefaultAccountAdapter):
    """Email/password signup disabled — Google only in production UI."""

    def is_open_for_signup(self, request):
        from django.conf import settings

        return getattr(settings, 'SHOW_MANUAL_AUTH', False)


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        user.first_name = (data.get('first_name') or '').strip()[:150]
        user.last_name = (data.get('last_name') or '').strip()[:150]
        email = (data.get('email') or user.email or '').strip().lower()
        if email:
            user.email = email
            if not user.username:
                user.username = email
        return user

    def save_user(self, request, sociallogin, form=None):
        was_new = not sociallogin.user.pk
        user = super().save_user(request, sociallogin, form=form)
        if not user.username:
            user.username = user.email
            user.save(update_fields=['username'])
        if was_new:
            get_or_create_subscription(user)
        return user
