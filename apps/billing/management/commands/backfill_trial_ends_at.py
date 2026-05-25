from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.billing.models import FREE_TRIAL_DAYS, Subscription
from apps.notifications.models import NotificationLevel
from apps.notifications.services import create_notification


class Command(BaseCommand):
    help = (
        'One-time backfill: set trial_ends_at = now + 7 days for all free accounts '
        'that have no trial_ends_at (legacy accounts). '
        'The daily billing.suspend_expired_trials task will suspend them after the grace period.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print affected accounts without making changes.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        grace_ends = timezone.now() + timezone.timedelta(days=FREE_TRIAL_DAYS)

        qs = Subscription.objects.filter(
            plan_slug=Subscription.Plan.FREE,
            status=Subscription.Status.ACTIVE,
            trial_ends_at__isnull=True,
        ).select_related('user')

        count = qs.count()
        if count == 0:
            self.stdout.write('No legacy free accounts found. Nothing to do.')
            return

        self.stdout.write(f'Found {count} legacy free account(s) with no trial_ends_at.')

        if dry_run:
            for sub in qs:
                self.stdout.write(f'  [DRY RUN] {sub.user.email} → trial_ends_at={grace_ends.date()}')
            self.stdout.write('Dry run complete. No changes made.')
            return

        for sub in qs:
            sub.trial_ends_at = grace_ends
            sub.save(update_fields=['trial_ends_at', 'updated_at'])
            create_notification(
                user_id=sub.user_id,
                title='Your free trial starts now',
                body=(
                    f'We\'ve started your {FREE_TRIAL_DAYS}-day free trial. '
                    'After that, redeem a plan to keep your account active.'
                ),
                level=NotificationLevel.INFO,
                link_url='/billing/redeem/',
            )
            self.stdout.write(f'  Updated {sub.user.email}')

        self.stdout.write(
            self.style.SUCCESS(
                f'Done. {count} account(s) given {FREE_TRIAL_DAYS}-day grace period ending {grace_ends.date()}.'
            )
        )
