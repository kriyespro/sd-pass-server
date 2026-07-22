"""
Let users add custom domains in the dashboard without SSH/env edits.

If ``Host`` matches ``Project.custom_hostname`` (or its www ↔ apex sibling) for an
active project, append both host forms to ``ALLOWED_HOSTS``. CSRF trusted origins
are added only after TXT verification.
"""
from __future__ import annotations

from django.conf import settings

from apps.projects.host_allowlist import (
    host_without_port,
    is_trusted_custom_hostname,
    project_has_custom_hostname,
    register_host_for_django,
)

# Built once at startup from ALLOWED_HOSTS — no Redis lookup needed for these.
_PLATFORM_HOSTS: frozenset[str] = frozenset()


def _get_platform_hosts() -> frozenset[str]:
    global _PLATFORM_HOSTS
    if not _PLATFORM_HOSTS:
        _PLATFORM_HOSTS = frozenset(
            h.lstrip('.').lower()
            for h in getattr(settings, 'ALLOWED_HOSTS', [])
            if h not in ('*', '')
        )
    return _PLATFORM_HOSTS


class DynamicAllowedHostsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        raw = (request.META.get('HTTP_HOST') or '').strip()
        if raw:
            host = host_without_port(raw).lower()
            if host and host not in _get_platform_hosts() and project_has_custom_hostname(host):
                register_host_for_django(host, trust_csrf=is_trusted_custom_hostname(host))
        return self.get_response(request)
