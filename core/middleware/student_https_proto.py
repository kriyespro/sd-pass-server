"""
When TLS terminates at nginx/Cloudflare and Traefik talks HTTP to Gunicorn, Django
still sees ``X-Forwarded-Proto: http`` (or missing) and ``SECURE_SSL_REDIRECT``
returns 301 to https in a loop for curl/tests that hit Traefik :9080 directly.

If ``STUDENT_TRUST_TRAEFIK_HTTPS`` is True, requests whose Host matches the student
platform (``{subdomain}.{STUDENT_APPS_BASE_DOMAIN}`` or the base domain) are treated
as HTTPS by setting ``X-Forwarded-Proto`` before ``SecurityMiddleware`` runs.

Only enable when public student URLs are always HTTPS (``STUDENT_SITE_PUBLIC_SCHEME=https``).
"""
from __future__ import annotations

from django.conf import settings

from core.middleware.student_static_site import _host_without_port


class StudentTraefikHttpsProtoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, 'STUDENT_TRUST_TRAEFIK_HTTPS', False):
            return self.get_response(request)
        if getattr(settings, 'STUDENT_SITE_PUBLIC_SCHEME', 'http') != 'https':
            return self.get_response(request)

        raw_host = request.META.get('HTTP_HOST', '')
        host = _host_without_port(raw_host)
        base = settings.STUDENT_APPS_BASE_DOMAIN.strip().strip('.').lower()
        if not base or not host:
            return self.get_response(request)

        if host != base and not host.endswith(f'.{base}'):
            return self.get_response(request)

        # Traefik often sends X-Forwarded-Proto: http on the internal hop; Django takes the
        # first comma-separated value, so "http, https" still counts as http. Replace fully
        # in META and WSGI environ so SecurityMiddleware sees HTTPS.
        request.META.pop('HTTP_X_FORWARDED_PROTO', None)
        request.META['HTTP_X_FORWARDED_PROTO'] = 'https'
        environ = getattr(request, 'environ', None)
        if environ is not None:
            environ.pop('HTTP_X_FORWARDED_PROTO', None)
            environ['HTTP_X_FORWARDED_PROTO'] = 'https'
            environ['wsgi.url_scheme'] = 'https'
            environ['HTTPS'] = 'on'
        return self.get_response(request)
