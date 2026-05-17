from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.deployments.services import project_site_dir
from apps.deployments.site_assets import optimize_site_assets
from apps.platform_ops.models import AssetOptimizationRun
from apps.platform_ops.services.cache_stats import get_redis_cache_stats
from apps.platform_ops.utils import format_bytes
from apps.projects.models import Project, ProjectStatus, ProjectType

logger = logging.getLogger(__name__)


def optimization_interval() -> timedelta:
    hours = int(getattr(settings, 'ASSET_OPTIMIZATION_INTERVAL_HOURS', 24) or 24)
    return timedelta(hours=max(hours, 1))


def _aggregate_stats(total: dict, site: dict) -> None:
    for key in (
        'css_files',
        'js_files',
        'image_files',
        'files_optimized',
        'bytes_before',
        'bytes_after',
        'bytes_saved',
    ):
        total[key] += site.get(key, 0)


def run_asset_optimization(*, run_id: int | None = None, user_id: int | None = None) -> AssetOptimizationRun:
    """Minify CSS/JS and optimize images for every active static site."""
    cache = get_redis_cache_stats()
    interval = optimization_interval()
    now = timezone.now()

    if run_id:
        run = AssetOptimizationRun.objects.get(pk=run_id)
        run.status = AssetOptimizationRun.Status.RUNNING
        run.save(update_fields=['status'])
    else:
        run = AssetOptimizationRun.objects.create(
            status=AssetOptimizationRun.Status.RUNNING,
            triggered_by_id=user_id,
            next_run_at=now + interval,
        )

    totals = {
        'css_files': 0,
        'js_files': 0,
        'image_files': 0,
        'files_optimized': 0,
        'bytes_before': 0,
        'bytes_after': 0,
        'bytes_saved': 0,
        'projects_processed': 0,
    }

    try:
        projects = Project.objects.filter(
            is_deleted=False,
            project_type=ProjectType.STATIC,
            status=ProjectStatus.RUNNING,
        )
        for project in projects:
            site_dir: Path = project_site_dir(project)
            if not site_dir.is_dir():
                continue
            stats = optimize_site_assets(site_dir)
            if stats.get('files_found', 0) == 0:
                continue
            totals['projects_processed'] += 1
            _aggregate_stats(totals, stats)

        run.status = AssetOptimizationRun.Status.DONE
        run.finished_at = timezone.now()
        run.next_run_at = run.finished_at + interval
        run.projects_processed = totals['projects_processed']
        run.css_files = totals['css_files']
        run.js_files = totals['js_files']
        run.image_files = totals['image_files']
        run.files_optimized = totals['files_optimized']
        run.bytes_before = totals['bytes_before']
        run.bytes_after = totals['bytes_after']
        run.bytes_saved = totals['bytes_saved']
        run.cache_used_memory_human = cache.get('used_memory_human', '')
        run.cache_peak_memory_human = cache.get('used_memory_peak_human', '')
        run.cache_keys = cache.get('keys', 0)
        run.save()
        logger.info(
            'platform_ops: asset optimization done — %s projects, saved %s',
            run.projects_processed,
            format_bytes(run.bytes_saved),
        )
    except Exception as exc:
        logger.exception('platform_ops: asset optimization failed')
        run.status = AssetOptimizationRun.Status.FAILED
        run.finished_at = timezone.now()
        run.error_message = str(exc)[:2000]
        run.next_run_at = timezone.now() + interval
        run.save()
        raise

    return run


def get_asset_optimization_dashboard() -> dict:
    """Context for Mission Control asset optimization panel."""
    latest = AssetOptimizationRun.objects.filter(
        status__in=(
            AssetOptimizationRun.Status.DONE,
            AssetOptimizationRun.Status.FAILED,
        )
    ).first()
    running = AssetOptimizationRun.objects.filter(
        status=AssetOptimizationRun.Status.RUNNING
    ).exists()
    pending = AssetOptimizationRun.objects.filter(
        status=AssetOptimizationRun.Status.PENDING
    ).exists()

    cache = get_redis_cache_stats()
    interval = optimization_interval()

    last_finished = latest.finished_at if latest else None
    in_progress = running or pending
    next_run = None
    if in_progress:
        next_run = None
    elif latest and latest.next_run_at:
        next_run = latest.next_run_at
    elif last_finished:
        next_run = last_finished + interval
    else:
        next_run = timezone.now()

    return {
        'asset_run': latest,
        'asset_running': in_progress,
        'asset_last_finished': last_finished,
        'asset_next_run': next_run,
        'asset_next_run_in_progress': in_progress,
        'asset_interval_hours': int(interval.total_seconds() // 3600),
        'cache_stats': cache,
        'bytes_saved_human': format_bytes(latest.bytes_saved if latest else 0),
    }
