from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from core.celery import app


@app.task(name='notifications.delete_old_read')
def delete_old_read_notifications() -> int:
    from apps.notifications.models import Notification

    days = getattr(settings, 'NOTIFICATION_RETENTION_DAYS', 90)
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = Notification.objects.filter(read_at__isnull=False, read_at__lt=cutoff).delete()
    return deleted
