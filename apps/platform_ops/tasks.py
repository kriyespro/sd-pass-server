from __future__ import annotations

from core.celery import app


@app.task(name='platform_ops.run_asset_optimization', bind=True, max_retries=0)
def run_asset_optimization_task(self, run_id: int) -> dict:
    from apps.platform_ops.services.asset_runner import run_asset_optimization

    run = run_asset_optimization(run_id=run_id)
    return {'run_id': run.pk, 'status': run.status, 'bytes_saved': run.bytes_saved}


@app.task(name='platform_ops.schedule_asset_optimization', bind=True, max_retries=0)
def scheduled_asset_optimization_task(self) -> dict:
    """Triggered by Celery beat at 4:10 AM IST (22:40 UTC). Creates a run and queues the worker."""
    from apps.platform_ops.models import AssetOptimizationRun

    if AssetOptimizationRun.objects.filter(
        status__in=(AssetOptimizationRun.Status.PENDING, AssetOptimizationRun.Status.RUNNING)
    ).exists():
        return {'skipped': True, 'reason': 'run already in progress'}
    run = AssetOptimizationRun.objects.create()
    run_asset_optimization_task.delay(run.pk)
    return {'run_id': run.pk, 'queued': True}


@app.task(name='platform_ops.create_platform_backup', bind=True, max_retries=0)
def create_platform_backup_task(self, backup_id: int) -> dict:
    from apps.platform_ops.services.backup import create_platform_backup

    backup = create_platform_backup(backup_id=backup_id)
    return {
        'backup_id': backup.pk,
        'status': backup.status,
        'size_bytes': backup.size_bytes,
    }
