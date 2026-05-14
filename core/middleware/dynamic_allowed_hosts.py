"""
Let users add custom domains in the dashboard without SSH/env edits.

If ``Host`` matches ``Project.custom_hostname`` for an active project, append that
host to ``ALLOWED_HOSTS``. CSRF trusted origins are added only after TXT verification.
"""
from __future__ import annotations

from apps.projects.host_allowlist import (
    is_trusted_custom_hostname,
    project_has_custom_hostname,
    register_host_for_django,
)


class DynamicAllowedHostsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        raw = (request.META.get('HTTP_HOST') or '').strip()
        if raw:
            host = raw.split(':')[0].lower()
            if host and project_has_custom_hostname(host):
                register_host_for_django(host, trust_csrf=is_trusted_custom_hostname(host))
        return self.get_response(request)
