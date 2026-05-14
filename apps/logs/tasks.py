from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from core.celery import app


@app.task(name='logs.delete_old_log_entries')
def delete_old_log_entries() -> int:
    from apps.logs.models import LogEntry

    days = getattr(settings, 'LOG_RETENTION_DAYS', 7)
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = LogEntry.objects.filter(created_at__lt=cutoff).delete()
    return deleted
