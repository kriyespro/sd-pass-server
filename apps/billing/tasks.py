from django.urls import reverse

from core.celery import app


@app.task(name='billing.suspend_expired_trials')
def suspend_expired_trials() -> dict:
    from django.utils import timezone

    from apps.notifications.models import NotificationLevel
    from apps.notifications.services import create_notification

    from .models import Subscription

    now = timezone.now()
    suspended_ids = []

    # Suspend expired 9-day test_plan (₹99 trial) users.
    expired_trials = Subscription.objects.filter(
        plan_slug=Subscription.Plan.TEST_PLAN,
        status=Subscription.Status.ACTIVE,
        current_period_end__lt=now,
    ).select_related('user')

    for sub in expired_trials:
        sub.status = Subscription.Status.SUSPENDED
        sub.save(update_fields=['status', 'updated_at'])
        suspended_ids.append(sub.user_id)
        create_notification(
            user_id=sub.user_id,
            title='Your 9-day trial has ended',
            body=(
                'Your ₹99 trial has expired and your account has been suspended. '
                'Purchase a plan to restore access.'
            ),
            level=NotificationLevel.WARNING,
            link_url=reverse('billing:redeem'),
        )

    # Also suspend any remaining active free-plan accounts (no more free tier).
    active_free = Subscription.objects.filter(
        plan_slug=Subscription.Plan.FREE,
        status=Subscription.Status.ACTIVE,
    ).select_related('user')

    for sub in active_free:
        sub.status = Subscription.Status.SUSPENDED
        sub.save(update_fields=['status', 'updated_at'])
        suspended_ids.append(sub.user_id)
        create_notification(
            user_id=sub.user_id,
            title='Free plan discontinued',
            body=(
                'The free plan is no longer available. '
                'Start with our ₹99 trial to restore access.'
            ),
            level=NotificationLevel.WARNING,
            link_url=reverse('billing:redeem'),
        )

    return {'suspended': len(suspended_ids), 'user_ids': suspended_ids}
