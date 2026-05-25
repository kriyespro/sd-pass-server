from django.urls import reverse

from core.celery import app


@app.task(name='billing.suspend_expired_trials')
def suspend_expired_trials() -> dict:
    from django.utils import timezone

    from apps.notifications.models import NotificationLevel
    from apps.notifications.services import create_notification

    from .models import Subscription

    now = timezone.now()
    expired = Subscription.objects.filter(
        plan_slug=Subscription.Plan.FREE,
        status=Subscription.Status.ACTIVE,
        trial_ends_at__lt=now,
    ).select_related('user')

    suspended_ids = []
    for sub in expired:
        sub.status = Subscription.Status.SUSPENDED
        sub.save(update_fields=['status', 'updated_at'])
        suspended_ids.append(sub.user_id)
        create_notification(
            user_id=sub.user_id,
            title='Your free trial has ended',
            body=(
                'Your 7-day free trial has expired and your account has been suspended. '
                'Redeem a plan to restore access.'
            ),
            level=NotificationLevel.WARNING,
            link_url=reverse('billing:redeem'),
        )

    return {'suspended': len(suspended_ids), 'user_ids': suspended_ids}
