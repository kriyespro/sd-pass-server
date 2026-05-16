from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from apps.accounts.models import User
from apps.billing.services import get_or_create_subscription


class AccountAdapter(DefaultAccountAdapter):
    """Block email/password signup forms only — does not affect Google OAuth."""

    def is_open_for_signup(self, request):
        from django.conf import settings

        return getattr(settings, 'SHOW_MANUAL_AUTH', False)


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        """Google sign-up / first-time Google login must stay open."""
        return True

    def pre_social_login(self, request, sociallogin):
        """
        Link Google to an existing manual (email/password) account when emails match.
        """
        if sociallogin.is_existing:
            return

        email = None
        if sociallogin.email_addresses:
            email = sociallogin.email_addresses[0].email
        if not email and sociallogin.user and getattr(sociallogin.user, 'email', None):
            email = sociallogin.user.email
        if not email and sociallogin.account:
            email = (sociallogin.account.extra_data or {}).get('email')

        if not email:
            return

        user = User.objects.filter(email__iexact=email.strip()).first()
        if user:
            sociallogin.connect(request, user)

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
            from apps.onboarding.services import get_or_create_onboarding

            get_or_create_onboarding(user)
        return user
