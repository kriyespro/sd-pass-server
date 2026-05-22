"""Background Celery task: optimize images in a deployed static site.

Runs at lowest OS priority (nice 19) and throttles to ~10% CPU by sleeping
9x the elapsed work time between each image.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from core.celery import app

_IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp'}
_CPU_FRACTION = 0.10  # target 10 % CPU; sleep = work * (1 - f) / f


def _throttled_optimize(img_path: Path, *, ultra: bool = False) -> tuple[int, int]:
    """Run one image through normal or ultra optimizer, then sleep to cap CPU."""
    from apps.deployments.image_optimizer import _optimize_image, _ultra_compress_image

    fn = _ultra_compress_image if ultra else _optimize_image
    t0 = time.perf_counter()
    result = fn(img_path)
    elapsed = time.perf_counter() - t0
    if elapsed > 0:
        time.sleep(elapsed * (1 - _CPU_FRACTION) / _CPU_FRACTION)
    return result


@app.task(name='deployments.compress_site_images', bind=True, max_retries=0)
def compress_site_images(self, project_id: int) -> dict:
    from apps.deployments.services import project_site_dir
    from apps.logs.models import LogKind
    from apps.logs.services import append_project_log
    from apps.notifications.models import NotificationLevel
    from apps.notifications.services import create_notification
    from apps.projects.models import Project

    # Lowest CPU priority so the task never starves other processes
    try:
        os.nice(19)
    except OSError:
        pass

    proj = Project.objects.filter(pk=project_id, is_deleted=False).first()
    if not proj:
        return {'error': 'project_not_found'}

    site_dir: Path = project_site_dir(proj)
    if not site_dir.is_dir():
        return {'error': 'site_dir_missing'}

    images = [
        p for p in site_dir.rglob('*')
        if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES
    ]

    if not images:
        append_project_log(proj, LogKind.SYSTEM, 'Image optimizer: no images found.')
        return {'files_found': 0, 'files_optimized': 0, 'bytes_saved': 0, 'kb_saved': 0.0,
                'ultra_files_optimized': 0, 'ultra_bytes_saved': 0}

    # --- Pass 1: normal compression ---
    norm_optimized = 0
    norm_bytes_saved = 0
    for img_path in images:
        orig, new = _throttled_optimize(img_path, ultra=False)
        if orig > 0 and new < orig:
            norm_optimized += 1
            norm_bytes_saved += orig - new

    # --- Pass 2: ultra compression ---
    ultra_optimized = 0
    ultra_bytes_saved = 0
    for img_path in images:
        if not img_path.exists():
            continue
        orig, new = _throttled_optimize(img_path, ultra=True)
        if orig > 0 and new < orig:
            ultra_optimized += 1
            ultra_bytes_saved += orig - new

    total_optimized = norm_optimized + ultra_optimized
    total_saved_kb = round((norm_bytes_saved + ultra_bytes_saved) / 1024, 1)
    found = len(images)

    if total_optimized == 0:
        append_project_log(
            proj, LogKind.SYSTEM,
            f'Image optimizer: {found} image(s) checked — already fully optimized.',
        )
        create_notification(
            user_id=proj.owner_id,
            title='✅ Images already optimized',
            body=f'{found} image(s) checked — nothing to compress.',
            level=NotificationLevel.INFO,
        )
    else:
        append_project_log(
            proj, LogKind.BUILD,
            f'Image optimizer: {found} found, normal pass saved {round(norm_bytes_saved/1024,1)} KB '
            f'({norm_optimized} files), ultra pass saved {round(ultra_bytes_saved/1024,1)} KB '
            f'({ultra_optimized} files). Total: {total_saved_kb} KB.',
        )
        create_notification(
            user_id=proj.owner_id,
            title='⚡ Image optimization complete',
            body=(
                f'Compressed {total_optimized} image(s) on "{proj.name}", '
                f'saving {total_saved_kb} KB total (normal + ultra pass).'
            ),
            level=NotificationLevel.SUCCESS,
        )

    return {
        'files_found': found,
        'files_optimized': norm_optimized,
        'bytes_saved': norm_bytes_saved,
        'kb_saved': round(norm_bytes_saved / 1024, 1),
        'ultra_files_optimized': ultra_optimized,
        'ultra_bytes_saved': ultra_bytes_saved,
        'ultra_kb_saved': round(ultra_bytes_saved / 1024, 1),
    }
