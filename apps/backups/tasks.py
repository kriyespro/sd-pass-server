from core.celery import app


@app.task(name='backups.run_scheduled_backups')
def run_scheduled_backups() -> int:
    """Placeholder: pg_dump + S3 (durga B1)."""
    return 0
