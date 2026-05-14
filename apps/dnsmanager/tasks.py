from core.celery import app


@app.task(name='dnsmanager.sync_cloudflare_dns')
def sync_cloudflare_dns(prev: dict) -> dict:
    from django.conf import settings

    from apps.dnsmanager.models import DnsRecord, DnsStatus
    from apps.dnsmanager.services import cloudflare_upsert_a_record
    from apps.domains.services import project_fqdn
    from apps.projects.models import Project

    if not prev.get('passed') or not prev.get('project_id'):
        return {**prev, 'dns': 'skipped'}

    if prev.get('traefik') == 'failed':
        return {**prev, 'dns': 'skipped_traefik_failed'}

    token = settings.CLOUDFLARE_API_TOKEN
    zone = settings.CLOUDFLARE_ZONE_ID
    ip = settings.PLATFORM_PUBLIC_IP
    if not (token and zone and ip):
        return {**prev, 'dns': 'skipped_missing_cloudflare_or_ip'}

    project = Project.objects.filter(pk=prev['project_id']).first()
    if not project:
        return {**prev, 'dns': 'skipped_no_project'}

    fqdn = project_fqdn(project)
    try:
        cf = cloudflare_upsert_a_record(fqdn, ip)
    except Exception as exc:  # noqa: BLE001
        DnsRecord.objects.update_or_create(
            project=project,
            fqdn=fqdn,
            defaults={
                'record_type': 'A',
                'target_ip': ip,
                'status': DnsStatus.FAILED,
                'last_error': str(exc),
            },
        )
        from apps.logs.models import LogKind
        from apps.logs.services import append_project_log

        append_project_log(
            project,
            LogKind.SYSTEM,
            f'Cloudflare DNS sync failed for {fqdn}: {exc}',
        )
        return {**prev, 'dns': 'failed', 'dns_error': str(exc)}

    DnsRecord.objects.update_or_create(
        project=project,
        fqdn=fqdn,
        defaults={
            'record_type': 'A',
            'target_ip': ip,
            'status': DnsStatus.APPLIED,
            'cloudflare_record_id': str(cf.get('id', '')),
            'last_error': '',
        },
    )
    from apps.logs.models import LogKind
    from apps.logs.services import append_project_log

    msg_action = cf.get('action', 'ok')
    append_project_log(
        project,
        LogKind.SYSTEM,
        f'Cloudflare DNS {msg_action} for {fqdn} → {ip} (record id {cf.get("id", "")}).',
    )
    return {**prev, 'dns': cf.get('action'), 'cloudflare_id': cf.get('id')}
