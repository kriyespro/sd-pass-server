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
        extract_ok, extract_msg = extract_static_site_from_zip(
            proj, Path(upload.file.path), subfolder=upload.deploy_subfolder or ''
        )
        if extract_ok:
            _sub = (upload.deploy_subfolder or '').strip('/')
            from apps.projects.models import Project as _Project, ProjectSubfolder
            _Project.objects.filter(pk=proj.pk).update(site_subfolder=_sub)
            ProjectSubfolder.objects.update_or_create(project=proj, path=_sub)
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
    elif proj.project_type == ProjectType.FLASK:
        from apps.deployments.flask_deploy import deploy_flask_project
        from apps.domains.services import write_project_router_file

        extract_ok, extract_msg = deploy_flask_project(proj, Path(upload.file.path))
        if extract_ok:
            proj.refresh_from_db()
            try:
                write_project_router_file(proj)
            except OSError as exc:
                append_project_log(proj, LogKind.SYSTEM, f'Traefik route update after Flask deploy failed: {exc}')
            append_project_log(proj, LogKind.BUILD, f'Flask app deployed: {extract_msg}')
        else:
            append_project_log(proj, LogKind.SYSTEM, f'Flask deploy failed: {extract_msg}')

    else:
        append_project_log(
            proj,
            LogKind.BUILD,
            'Deployment recorded — set project type to “Static” or “Flask” for automatic hosting.',
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

    from core.middleware.student_static_site import invalidate_site_host_cache
    invalidate_site_host_cache(proj)

    base = settings.STUDENT_APPS_BASE_DOMAIN.strip().strip('.')
    fqdn = f'{proj.subdomain}.{base}'
    site_port = getattr(settings, 'STUDENT_SITE_HTTP_PORT', 0) or 0
    scheme = getattr(settings, 'STUDENT_SITE_PUBLIC_SCHEME', 'http') or 'http'
    if scheme not in ('http', 'https'):
        scheme = 'http'
    site_url = (
        f'{scheme}://{fqdn}:{site_port}/' if site_port else f'{scheme}://{fqdn}/'
    )
    subfolder = (upload.deploy_subfolder or '').strip('/')
    if subfolder:
        site_url = site_url + subfolder + '/'
    if proj.project_type == ProjectType.STATIC and extract_ok:
        link_url = site_url
        body = f'Your static files are published. Open {site_url}'
        if extract_msg == 'extracted_no_index_html':
            body += ' (add index.html at the ' + ('subfolder root' if subfolder else 'ZIP root') + ' for the page to load).'
    elif proj.project_type == ProjectType.FLASK and extract_ok:
        link_url = site_url
        body = f'Your Flask app is live at {site_url} — first request may take a few seconds while gunicorn starts.'
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

    from apps.onboarding.services import complete_onboarding_on_deploy

    if proj.project_type != ProjectType.STATIC or extract_ok:
        complete_onboarding_on_deploy(proj.owner)

    # Queue AI image compression for static sites
    if proj.project_type == ProjectType.STATIC and extract_ok:
        create_notification(
            user_id=proj.owner_id,
            title='🤖 AI Image Optimizer is working…',
            body=(
                'Our best AI is scanning and compressing your site images in the background. '
                'You will get another alert when it\'s done!'
            ),
            level=NotificationLevel.INFO,
        )
        from apps.platform_ops.services.image_compression import queue_image_compression

        queue_image_compression(proj, trigger='upload')

    return {**scan_result, 'deploy': 'stub_recorded'}
