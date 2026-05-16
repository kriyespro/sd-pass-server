"""Background Celery task: optimize images in a deployed static site."""
from __future__ import annotations

from core.celery import app


@app.task(name='deployments.compress_site_images', bind=True, max_retries=0)
def compress_site_images(self, project_id: int) -> dict:
    from pathlib import Path

    from apps.deployments.services import project_site_dir
    from apps.logs.models import LogKind
    from apps.logs.services import append_project_log
    from apps.notifications.models import NotificationLevel
    from apps.notifications.services import create_notification
    from apps.projects.models import Project

    from .image_optimizer import optimize_site_images

    proj = Project.objects.filter(pk=project_id, is_deleted=False).first()
    if not proj:
        return {'error': 'project_not_found'}

    site_dir: Path = project_site_dir(proj)
    if not site_dir.is_dir():
        return {'error': 'site_dir_missing'}

    result = optimize_site_images(site_dir)
    found = result['files_found']
    optimized = result['files_optimized']
    kb_saved = result['kb_saved']

    if found == 0:
        append_project_log(proj, LogKind.SYSTEM, 'AI Optimizer: no images found in site.')
        return result

    if optimized == 0:
        append_project_log(
            proj,
            LogKind.SYSTEM,
            f'AI Optimizer: {found} image(s) checked — already optimized, no changes needed.',
        )
        create_notification(
            user_id=proj.owner_id,
            title='✅ Images already optimized',
            body=f'{found} image(s) checked — all are already in great shape!',
            level=NotificationLevel.INFO,
        )
        return result

    append_project_log(
        proj,
        LogKind.BUILD,
        f'AI Optimizer: compressed {optimized}/{found} image(s), saved {kb_saved} KB.',
    )
    create_notification(
        user_id=proj.owner_id,
        title='🎨 Image optimization complete',
        body=(
            f'Our AI compressed {optimized} image(s) on your site "{proj.name}", '
            f'saving {kb_saved} KB — your site now loads faster!'
        ),
        level=NotificationLevel.SUCCESS,
    )
    return result
