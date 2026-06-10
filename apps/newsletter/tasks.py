import logging

from django.utils import timezone

from core.celery import app

logger = logging.getLogger(__name__)


@app.task(name='newsletter.sync_all_users', bind=True, max_retries=0)
def sync_all_users(self, sync_id: int = None):
    from django.contrib.auth import get_user_model
    from .models import NewsletterSync
    from .services import sync_user

    User = get_user_model()

    if sync_id:
        try:
            sync = NewsletterSync.objects.get(pk=sync_id)
        except NewsletterSync.DoesNotExist:
            return
    else:
        sync = NewsletterSync.objects.create()

    users = list(
        User.objects.filter(is_active=True)
        .values('email', 'first_name', 'last_name')
    )
    sync.total = len(users)
    sync.status = NewsletterSync.Status.RUNNING
    sync.started_at = timezone.now()
    sync.save(update_fields=['total', 'status', 'started_at'])

    synced = skipped = failed = 0
    for u in users:
        ok = sync_user(u['email'], u['first_name'], u['last_name'])
        if ok:
            synced += 1
        else:
            failed += 1

    sync.synced = synced
    sync.skipped = skipped
    sync.failed = failed
    sync.status = NewsletterSync.Status.DONE if failed == 0 else NewsletterSync.Status.FAILED
    sync.finished_at = timezone.now()
    sync.save(update_fields=['synced', 'skipped', 'failed', 'status', 'finished_at'])
    logger.info('newsletter sync done: %s/%s synced, %s failed', synced, len(users), failed)
    return {'synced': synced, 'failed': failed, 'total': len(users)}
