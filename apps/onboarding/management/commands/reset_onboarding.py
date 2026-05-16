from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.onboarding.models import UserOnboarding


class Command(BaseCommand):
    help = 'Reset guided onboarding for a user (by email) so the wizard shows again on /projects/.'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='User email address')

    def handle(self, *args, **options):
        email = options['email'].strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            raise CommandError(f'No user with email {email!r}')

        ob, _ = UserOnboarding.objects.get_or_create(user=user)
        ob.step_completed = 0
        ob.skipped = False
        ob.completed_at = None
        ob.save(update_fields=['step_completed', 'skipped', 'completed_at'])
        self.stdout.write(self.style.SUCCESS(f'Onboarding reset for {user.email}'))
