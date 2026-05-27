"""One-time command: suspend all active free-plan accounts (free trial removed)."""
from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone


class Command(BaseCommand):
    help = (
        'Suspend all active free-plan subscriptions. '
        'Run once after removing the free trial. '
        'Use --dry-run to preview without making changes.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview only, no DB writes.')
        parser.add_argument('--notify', action='store_true', help='Send in-app notification to each user.')

    def handle(self, *args, **options):
        from apps.billing.models import Subscription
        dry_run = options['dry_run']
        notify = options['notify']

        qs = Subscription.objects.filter(
            plan_slug=Subscription.Plan.FREE,
            status=Subscription.Status.ACTIVE,
        ).select_related('user')

        count = qs.count()
        if count == 0:
            self.stdout.write('No active free-plan accounts found. Nothing to do.')
            return

        self.stdout.write(f'Found {count} active free-plan account(s).')
        if dry_run:
            for sub in qs:
                self.stdout.write(f'  [DRY RUN] Would suspend: {sub.user.email}')
            self.stdout.write(self.style.WARNING('Dry run complete — no changes made.'))
            return

        link = reverse('billing:redeem')
        suspended = 0
        for sub in qs:
            sub.status = Subscription.Status.SUSPENDED
            sub.save(update_fields=['status', 'updated_at'])
            suspended += 1
            self.stdout.write(f'  Suspended: {sub.user.email}')
            if notify:
                try:
                    from apps.notifications.models import NotificationLevel
                    from apps.notifications.services import create_notification
                    create_notification(
                        user_id=sub.user_id,
                        title='Free plan discontinued',
                        body=(
                            'The free plan is no longer available. '
                            'Start with our ₹99 trial to restore access.'
                        ),
                        level=NotificationLevel.WARNING,
                        link_url=link,
                    )
                except Exception as exc:
                    self.stderr.write(f'    Notification failed for {sub.user.email}: {exc}')

        self.stdout.write(self.style.SUCCESS(f'Done. Suspended {suspended} account(s).'))
