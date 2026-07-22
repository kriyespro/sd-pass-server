"""Clear stale custom-host allowlist cache and optionally diagnose www↔apex."""
from __future__ import annotations

from django.core.cache import cache
from django.core.management.base import BaseCommand

from apps.projects.host_allowlist import (
    hostname_aliases,
    invalidate_custom_host_cache,
    is_trusted_custom_hostname,
    project_has_custom_hostname,
    sibling_hostname,
)
from apps.projects.models import Project


class Command(BaseCommand):
    help = (
        'Invalidate custom-hostname allowlist cache (fixes stale www 400s). '
        'Pass a hostname to also print alias / DB / Traefik diagnostics.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'hostname',
            nargs='?',
            default='',
            help='Optional hostname to diagnose (e.g. www.example.com)',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Invalidate allowlist cache for every project custom hostname',
        )

    def handle(self, *args, **options):
        host = (options.get('hostname') or '').strip().lower().rstrip('.')
        clear_all = bool(options.get('all'))

        if clear_all or not host:
            n = 0
            qs = (
                Project.objects.filter(is_deleted=False)
                .exclude(custom_hostname__isnull=True)
                .exclude(custom_hostname='')
                .only('custom_hostname')
            )
            for p in qs.iterator():
                invalidate_custom_host_cache(p.custom_hostname)
                n += 1
            # Also drop common legacy cache key prefixes from before v2.
            try:
                cache.delete_many([])  # no-op; document Redis SCAN for ops
            except Exception:  # noqa: BLE001
                pass
            self.stdout.write(self.style.SUCCESS(
                f'Invalidated allowlist cache for {n} custom hostname(s).'
            ))

        if not host:
            self.stdout.write(
                'Tip: also flush Redis keys if problems remain:\n'
                '  docker compose -f docker-compose.prod.yml --env-file .env.prod exec redis '
                'redis-cli KEYS "projects:allow_host*"\n'
                '  docker compose -f docker-compose.prod.yml --env-file .env.prod exec redis '
                'redis-cli --scan --pattern "projects:allow_host*" | '
                'xargs -r -n 100 redis-cli DEL'
            )
            return

        invalidate_custom_host_cache(host)
        aliases = sorted(hostname_aliases(host))
        sib = sibling_hostname(host)
        self.stdout.write(f'Host:      {host}')
        self.stdout.write(f'Sibling:   {sib or "(none)"}')
        self.stdout.write(f'Aliases:   {", ".join(aliases)}')
        self.stdout.write(f'Allowlist: {project_has_custom_hostname(host)}')
        self.stdout.write(f'Verified:  {is_trusted_custom_hostname(host)}')

        for alias in aliases:
            p = (
                Project.objects.filter(custom_hostname__iexact=alias, is_deleted=False)
                .only('id', 'subdomain', 'custom_hostname', 'custom_hostname_verified', 'owner_id')
                .first()
            )
            if p:
                self.stdout.write(
                    f'DB match:  pk={p.pk} subdomain={p.subdomain} '
                    f'saved={p.custom_hostname} verified={p.custom_hostname_verified}'
                )
                break
        else:
            self.stdout.write(self.style.ERROR('DB match:  none — domain not saved on any project'))

        self.stdout.write(
            '\nDNS check (from this container):\n'
            f'  getent hosts {host} || true\n'
            f'  getent hosts {sib} || true\n'
            '\nHTTP probe:\n'
            f'  curl -sI -H "Host: {host}" http://127.0.0.1:8000/ | head -5\n'
            f'  curl -sI https://{host}/ | head -8'
        )
