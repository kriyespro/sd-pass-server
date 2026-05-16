"""Mark onboarding complete for users who already have projects (one-time prod fix)."""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.onboarding.services import auto_complete_legacy_onboarding, get_or_create_onboarding


class Command(BaseCommand):
    help = 'Complete onboarding for existing students who already have active projects.'

    def handle(self, *args, **options):
        User = get_user_model()
        updated = 0
        for user in User.objects.filter(is_active=True).iterator():
            ob = get_or_create_onboarding(user)
            if auto_complete_legacy_onboarding(user, ob):
                updated += 1
        self.stdout.write(self.style.SUCCESS(f'Completed onboarding for {updated} user(s).'))
