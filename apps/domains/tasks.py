from core.celery import app


@app.task(name='domains.apply_traefik_route')
def apply_traefik_route(prev: dict) -> dict:
    from apps.domains.models import ProjectRoute, RouteStatus
    from apps.domains.services import project_fqdn, write_project_router_file
    from apps.projects.models import Project

    if not prev.get('passed') or not prev.get('project_id'):
        return {**prev, 'traefik': 'skipped'}

    project = Project.objects.filter(pk=prev['project_id']).first()
    if not project:
        return {**prev, 'traefik': 'skipped_no_project'}

    fqdn_guess = ''
    try:
        fqdn_guess = project_fqdn(project)
    except Exception:  # noqa: BLE001
        fqdn_guess = project.subdomain

    try:
        path, fqdn = write_project_router_file(project)
    except Exception as exc:  # noqa: BLE001
        ProjectRoute.objects.update_or_create(
            project=project,
            defaults={
                'fqdn': fqdn_guess,
                'config_path': '',
                'status': RouteStatus.FAILED,
                'last_error': str(exc),
            },
        )
        from apps.logs.models import LogKind
        from apps.logs.services import append_project_log

        append_project_log(
            project,
            LogKind.SYSTEM,
            f'Traefik dynamic route failed: {exc}',
        )
        return {**prev, 'traefik': 'failed', 'traefik_error': str(exc)}

    ProjectRoute.objects.update_or_create(
        project=project,
        defaults={
            'fqdn': fqdn,
            'config_path': str(path),
            'status': RouteStatus.APPLIED,
            'last_error': '',
        },
    )
    from apps.logs.models import LogKind
    from apps.logs.services import append_project_log

    append_project_log(
        project,
        LogKind.SYSTEM,
        f'Traefik route applied for {fqdn} (config {path}).',
    )
    return {**prev, 'traefik': 'applied', 'fqdn': fqdn, 'traefik_path': str(path)}


@app.task(name='domains.verify_single_custom_domain')
def verify_single_custom_domain(project_id: int) -> dict:
    """
    Verify a student's custom domain by checking its A record points to
    PLATFORM_PUBLIC_IP (primary). Falls back to legacy TXT challenge if the
    project still has a challenge token and no public IP is configured.
    """
    from django.conf import settings
    from django.urls import reverse

    from apps.domains.services import write_project_router_file
    from apps.domains.verification import (
        a_record_matches_ip,
        challenge_txt_present,
        domain_via_cloudflare_proxy,
        local_http_probe,
    )
    from apps.logs.models import LogKind
    from apps.logs.services import append_project_log
    from apps.notifications.models import NotificationLevel
    from apps.notifications.services import create_notification
    from apps.projects.host_allowlist import invalidate_custom_host_cache
    from apps.projects.models import Project

    project = Project.objects.filter(pk=project_id, is_deleted=False).first()
    if not project:
        return {'ok': False, 'reason': 'missing_project'}
    host = (project.custom_hostname or '').strip()
    if not host:
        return {'ok': True, 'skipped': 'no_hostname'}
    if project.custom_hostname_verified:
        return {'ok': True, 'skipped': 'already_verified'}

    platform_ip = (getattr(settings, 'PLATFORM_PUBLIC_IP', '') or '').strip()
    gunicorn_port = int(getattr(settings, 'STUDENT_GUNICORN_PORT', 9898) or 9898)
    verified = False
    method = 'none'

    # 1. Direct A-record match (grey cloud / no proxy)
    if platform_ip:
        verified = a_record_matches_ip(host, platform_ip)
        if verified:
            method = 'a_record_direct'

    # 2. Cloudflare orange-cloud proxy: DNS shows CF IPs → probe locally
    if not verified and domain_via_cloudflare_proxy(host):
        if local_http_probe(host, gunicorn_port):
            verified = True
            method = 'cloudflare_proxy_probe'
        else:
            append_project_log(
                project,
                LogKind.SYSTEM,
                f'Custom domain check for {host}: Cloudflare proxy detected but our '
                f'server did not respond for that hostname. Check the A record points '
                f'to {platform_ip or "this server"} in Cloudflare DNS.',
            )
            return {'ok': True, 'verified': False, 'method': 'cloudflare_probe_failed'}

    # 3. Legacy TXT challenge fallback
    if not verified:
        token = (project.custom_domain_challenge_token or '').strip()
        if token:
            verified = challenge_txt_present(host, token)
            if verified:
                method = 'txt'

    if not verified:
        append_project_log(
            project,
            LogKind.SYSTEM,
            f'Custom domain check for {host}: A record does not yet point to '
            f'{platform_ip or "server IP"}. Retry in a few minutes.',
        )
        return {'ok': True, 'verified': False, 'method': method}

    Project.objects.filter(pk=project_id).update(custom_hostname_verified=True)
    invalidate_custom_host_cache(host)
    project.refresh_from_db()
    try:
        write_project_router_file(project)
    except OSError as exc:
        append_project_log(
            project,
            LogKind.SYSTEM,
            f'Custom domain verified for {host} (via {method}), but Traefik route file failed: {exc}',
        )
        return {'ok': True, 'verified': True, 'traefik_error': str(exc)}

    append_project_log(
        project,
        LogKind.SYSTEM,
        f'Custom domain verified for {host} (via {method}); Traefik route updated.',
    )
    create_notification(
        user_id=project.owner_id,
        title='Custom domain verified',
        body=f'{host} is now active. Your site is accessible at https://{host}/',
        level=NotificationLevel.SUCCESS,
        link_url=reverse('projects:domain', kwargs={'slug': project.slug}),
    )
    return {'ok': True, 'verified': True, 'method': method}


@app.task(name='domains.poll_custom_domain_verification')
def poll_custom_domain_verification() -> dict:
    from apps.projects.models import Project

    ids = list(
        Project.objects.filter(is_deleted=False, custom_hostname_verified=False)
        .exclude(custom_hostname__isnull=True)
        .exclude(custom_hostname='')
        .exclude(custom_domain_challenge_token='')
        .values_list('pk', flat=True)[:200]
    )
    for pk in ids:
        verify_single_custom_domain.delay(pk)
    return {'queued': len(ids)}
