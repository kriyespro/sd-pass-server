from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string


def project_fqdn(project) -> str:
    base = settings.STUDENT_APPS_BASE_DOMAIN.strip().strip('.')
    return f'{project.subdomain}.{base}'


def write_project_router_file(project) -> tuple[Path, str]:
    """Render Traefik file-provider YAML for one project and write it to TRAEFIK_DYNAMIC_DIR."""
    fqdn = project_fqdn(project)
    router_name = f'proj{project.pk}'
    service_name = f'proj{project.pk}-svc'
    extra_hosts: list[str] = []
    raw = (getattr(project, 'custom_hostname', None) or '').strip().rstrip('.')
    verified = bool(getattr(project, 'custom_hostname_verified', False))
    if raw and raw.lower() != fqdn.lower() and verified:
        extra_hosts.append(raw.lower())
    content = render_to_string(
        'traefik/project_route.yml.jinja',
        {
            'router_name': router_name,
            'service_name': service_name,
            'host': fqdn,
            'extra_hosts': extra_hosts,
            'entry_points': settings.TRAEFIK_ENTRYPOINTS,
            'cert_resolver': settings.TRAEFIK_CERT_RESOLVER,
            'upstream_url': settings.TRAEFIK_UPSTREAM_URL,
            'use_tls': getattr(settings, 'TRAEFIK_TLS_ON_PROJECT_ROUTES', True),
        },
    )
    out_dir = settings.TRAEFIK_DYNAMIC_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f'{project.subdomain}.yml'
    path.write_text(content, encoding='utf-8')
    return path, fqdn


def remove_project_router_file(project) -> None:
    """Remove Traefik file-provider YAML for this project if it exists (e.g. after delete)."""
    out_dir = settings.TRAEFIK_DYNAMIC_DIR
    path = out_dir / f'{project.subdomain}.yml'
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
