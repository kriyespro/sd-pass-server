from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from django.utils import timezone

from apps.deployments.services import project_site_dir
from apps.platform_ops.models import ImageCompressionLog
from apps.projects.models import Project, ProjectType

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp'}


def project_has_images(project: Project) -> bool:
    root = project_site_dir(project)
    if not root.is_dir():
        return False
    for path in root.rglob('*'):
        if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES:
            return True
    return False


def queue_image_compression(project: Project, *, trigger: str = 'upload') -> ImageCompressionLog | None:
    """Create a log row immediately, then queue Celery (visible in Mission Control)."""
    if project.project_type != ProjectType.STATIC:
        return None
    log = ImageCompressionLog.objects.create(
        project=project,
        status=ImageCompressionLog.Status.RUNNING,
        trigger=trigger,
    )
    from apps.deployments.compress_task import compress_site_images

    compress_site_images.delay(project.pk, log_id=log.pk, trigger=trigger)
    return log


def expire_stale_image_compression_logs(*, minutes: int = 90) -> int:
    cutoff = timezone.now() - timedelta(minutes=minutes)
    return ImageCompressionLog.objects.filter(
        status=ImageCompressionLog.Status.RUNNING,
        started_at__lt=cutoff,
    ).update(
        status=ImageCompressionLog.Status.FAILED,
        finished_at=timezone.now(),
        error_message='Timed out — is the Celery worker running?',
    )


def backfill_missing_image_logs(*, limit: int = 50, run_compression: bool = True) -> int:
    """
    Create compression jobs for static sites with images but no log yet.
    Returns number of projects queued.
    """
    queued = 0
    projects = Project.objects.filter(
        is_deleted=False,
        project_type=ProjectType.STATIC,
    ).order_by('-created_at')
    for project in projects:
        if queued >= limit:
            break
        if ImageCompressionLog.objects.filter(project=project).exists():
            continue
        if not project_has_images(project):
            continue
        if run_compression:
            queue_image_compression(project, trigger=ImageCompressionLog.Trigger.SCHEDULED)
        else:
            ImageCompressionLog.objects.create(
                project=project,
                status=ImageCompressionLog.Status.DONE,
                trigger=ImageCompressionLog.Trigger.SCHEDULED,
                finished_at=timezone.now(),
            )
        queued += 1
    return queued
