from core.celery import app


@app.task(name='deployments.after_upload_scan')
def deploy_after_scan(scan_result: dict) -> dict:
    from pathlib import Path

    from django.conf import settings
    from django.urls import reverse

    from apps.deployments.models import Deployment, DeploymentStatus
    from apps.deployments.services import (
        extract_static_site_from_zip,
        write_runtime_env_snapshot,
    )
    from apps.envmanager.services import decrypted_env_for_project
    from apps.logs.models import LogKind
    from apps.logs.services import append_project_log
    from apps.notifications.models import NotificationLevel
    from apps.notifications.services import create_notification
    from apps.projects.models import ProjectType
    from apps.uploads.models import ProjectUpload

    if not scan_result.get('passed'):
        upload_id = scan_result.get('upload_id')
        if upload_id:
            upl = ProjectUpload.objects.select_related('project').filter(pk=upload_id).first()
            if upl:
                append_project_log(
                    upl.project,
                    LogKind.SYSTEM,
                    'Deploy step skipped: upload did not pass the security scan.',
                )
        return scan_result

    upload_id = scan_result.get('upload_id')
    upload = (
        ProjectUpload.objects.select_related('project')
        .filter(pk=upload_id)
        .first()
    )
    if not upload:
        return {**scan_result, 'deploy': 'skipped_no_upload'}

    proj = upload.project
    extract_ok = False
    extract_msg = ''

    Deployment.objects.create(
        project=proj,
        upload=upload,
        status=DeploymentStatus.SUCCEEDED,
        log='ZIP processed: static sites unpack to data/sites/<id> when project type is Static.',
    )

    if proj.project_type == ProjectType.STATIC:
        extract_ok, extract_msg = extract_static_site_from_zip(proj, Path(upload.file.path))
        if extract_ok:
            append_project_log(
                proj,
                LogKind.BUILD,
                f'Static site published for host access ({extract_msg}).',
            )
        else:
            append_project_log(
                proj,
                LogKind.SYSTEM,
                f'Static site step: {extract_msg}',
            )
    else:
        append_project_log(
            proj,
            LogKind.BUILD,
            'Static hosting skipped — set project type to “Static” for HTML/CSS/JS ZIP sites.',
        )

    env_plain = decrypted_env_for_project(proj)
    if proj.project_type == ProjectType.STATIC:
        write_runtime_env_snapshot(proj, env_plain if extract_ok else {})
        if extract_ok and env_plain:
            append_project_log(
                proj,
                LogKind.BUILD,
                f'Runtime env snapshot updated ({len(env_plain)} key(s); values not logged).',
            )
    elif env_plain:
        write_runtime_env_snapshot(proj, env_plain)
        append_project_log(
            proj,
            LogKind.BUILD,
            f'{len(env_plain)} environment variable(s) stored for future runtime (values not logged).',
        )

    append_project_log(
        proj,
        LogKind.BUILD,
        'Deployment record created after successful scan.',
    )

    base = settings.STUDENT_APPS_BASE_DOMAIN.strip().strip('.')
    fqdn = f'{proj.subdomain}.{base}'
    site_port = getattr(settings, 'STUDENT_SITE_HTTP_PORT', 0) or 0
    site_url = f'http://{fqdn}:{site_port}/' if site_port else f'http://{fqdn}/'
    if proj.project_type == ProjectType.STATIC and extract_ok:
        link_url = site_url
        body = f'Your static files are published. Open {site_url}'
        if extract_msg == 'extracted_no_index_html':
            body += ' (add index.html at the ZIP root for the / page).'
    else:
        link_url = reverse('projects:logs', kwargs={'slug': proj.slug})
        body = 'Your upload passed the scan. See project logs for details.'

    create_notification(
        user_id=proj.owner_id,
        title='Deployment recorded',
        body=body,
        level=NotificationLevel.SUCCESS,
        link_url=link_url,
    )
    return {**scan_result, 'deploy': 'stub_recorded'}
