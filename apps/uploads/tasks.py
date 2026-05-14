from celery import chain

from core.celery import app


@app.task(name='uploads.enqueue_upload_pipeline')
def enqueue_upload_pipeline(upload_id: int) -> None:
    from apps.deployments.tasks import deploy_after_scan
    from apps.dnsmanager.tasks import sync_cloudflare_dns
    from apps.domains.tasks import apply_traefik_route
    from apps.security.tasks import scan_upload

    chain(
        scan_upload.s(upload_id),
        deploy_after_scan.s(),
        apply_traefik_route.s(),
        sync_cloudflare_dns.s(),
    ).delay()
