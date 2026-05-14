"""
When TLS terminates at nginx/Cloudflare and Traefik talks HTTP to Gunicorn, Django
still sees ``X-Forwarded-Proto: http`` and ``SECURE_SSL_REDIRECT`` returns 301 in a
redirect loop.

If ``STUDENT_TRUST_TRAEFIK_HTTPS`` is True, requests whose Host either:
  • matches ``{subdomain}.{STUDENT_APPS_BASE_DOMAIN}`` / the base domain itself, OR
  • is a verified custom hostname stored in the Project model

are treated as HTTPS by injecting ``X-Forwarded-Proto: https`` before
``SecurityMiddleware`` runs.

Only enable when all public student URLs are served over HTTPS
(``STUDENT_SITE_PUBLIC_SCHEME=https``).

Custom-hostname lookups are cached in Django's cache for 60 s to avoid per-request
DB queries.
"""
from __future__ import annotations

import time

from django.conf import settings

from core.middleware.student_static_site import _host_without_port

# Simple in-process cache: {hostname: (bool, expires_ts)}
_custom_host_cache: dict[str, tuple[bool, float]] = {}
_CACHE_TTL = 60  # seconds


def _is_verified_custom_host(host: str) -> bool:
    """Return True if *host* is a verified custom hostname for any Project."""
    now = time.monotonic()
    entry = _custom_host_cache.get(host)
    if entry is not None and entry[1] > now:
        return entry[0]
    try:
        from apps.projects.models import Project  # avoid circular import at module level
        verified = Project.objects.filter(
            custom_hostname__iexact=host,
            custom_hostname_verified=True,
        ).exists()
    except Exception:  # noqa: BLE001
        verified = False
    _custom_host_cache[host] = (verified, now + _CACHE_TTL)
    return verified


def _patch_https(request) -> None:
    """Inject X-Forwarded-Proto: https into request META and WSGI environ."""
    request.META.pop('HTTP_X_FORWARDED_PROTO', None)
    request.META['HTTP_X_FORWARDED_PROTO'] = 'https'
    environ = getattr(request, 'environ', None)
    if environ is not None:
        environ.pop('HTTP_X_FORWARDED_PROTO', None)
        environ['HTTP_X_FORWARDED_PROTO'] = 'https'
        environ['wsgi.url_scheme'] = 'https'
        environ['HTTPS'] = 'on'


class StudentTraefikHttpsProtoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, 'STUDENT_TRUST_TRAEFIK_HTTPS', False):
            return self.get_response(request)
        if getattr(settings, 'STUDENT_SITE_PUBLIC_SCHEME', 'http') != 'https':
            return self.get_response(request)

        raw_host = request.META.get('HTTP_HOST', '')
        host = _host_without_port(raw_host).lower()
        if not host:
            return self.get_response(request)

        base = settings.STUDENT_APPS_BASE_DOMAIN.strip().strip('.').lower()

        # Match platform subdomain (e.g. radha.apps.crorepatinetwork.com) or base domain
        if base and (host == base or host.endswith(f'.{base}')):
            _patch_https(request)
            return self.get_response(request)

        # Match verified custom hostnames (e.g. dulhanindia.in)
        if _is_verified_custom_host(host):
            _patch_https(request)
            return self.get_response(request)

        return self.get_response(request)
