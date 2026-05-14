from core.celery import app


@app.task(name='quotas.snapshot_all_users')
def snapshot_all_users() -> int:
    """
    Placeholder until docker stats → DB (durga Q2). Writes one row per active user.
    """
    from django.contrib.auth import get_user_model

    from apps.projects.models import Project
    from apps.quotas.models import QuotaUsage

    User = get_user_model()
    n = 0
    for user in User.objects.filter(is_active=True).iterator():
        running = Project.objects.filter(
            owner=user, is_deleted=False, status='running'
        ).count()
        QuotaUsage.objects.create(
            user=user,
            ram_mb_used=0,
            cpu_percent=0,
            disk_gb_used=0,
            projects_running=running,
            note='stub: connect docker stats in worker',
        )
        n += 1
    return n
