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

    from apps.deployments.site_assets import optimize_site_assets

    proj = Project.objects.filter(pk=project_id, is_deleted=False).first()
    if not proj:
        return {'error': 'project_not_found'}

    site_dir: Path = project_site_dir(proj)
    if not site_dir.is_dir():
        return {'error': 'site_dir_missing'}

    result = optimize_site_assets(site_dir)
    found = result.get('files_found', 0)
    optimized = result.get('files_optimized', 0)
    kb_saved = result.get('kb_saved', 0)

    if found == 0:
        append_project_log(proj, LogKind.SYSTEM, 'Asset optimizer: no CSS, JS, or images found.')
        return result

    if optimized == 0:
        append_project_log(
            proj,
            LogKind.SYSTEM,
            f'Asset optimizer: {found} file(s) checked — already optimized.',
        )
        create_notification(
            user_id=proj.owner_id,
            title='✅ Site assets already optimized',
            body=f'{found} file(s) checked — CSS, JS, and images look good.',
            level=NotificationLevel.INFO,
        )
        return result

    append_project_log(
        proj,
        LogKind.BUILD,
        f'Asset optimizer: compressed {optimized}/{found} file(s), saved {kb_saved} KB.',
    )
    create_notification(
        user_id=proj.owner_id,
        title='⚡ Site optimization complete',
        body=(
            f'We optimized {optimized} file(s) on "{proj.name}" '
            f'(CSS, JS, images), saving {kb_saved} KB.'
        ),
        level=NotificationLevel.SUCCESS,
    )
    return result
