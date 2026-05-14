"""
Fix Django ``DisallowedHost`` (HTTP 400) when nginx forwards with a bad ``Host``
(e.g. ``127.0.0.1:9898``) but sends a correct ``X-Forwarded-Host`` (e.g. the public
domain).

**Security:** only enable ``RECOVER_PROXY_HOST_FROM_FORWARDED`` when Gunicorn is
**not** reachable from the public internet on that port — set
``WEB_HTTP_BIND=127.0.0.1`` in ``.env.prod`` so Docker publishes ``127.0.0.1:9898``.
Otherwise a remote client could spoof ``X-Forwarded-Host``.
"""

from __future__ import annotations

from django.conf import settings
from django.http.request import split_domain_port, validate_host


class RecoverProxyHostMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, 'RECOVER_PROXY_HOST_FROM_FORWARDED', False):
            return self.get_response(request)

        raw = (request.META.get('HTTP_HOST') or '').strip()
        if not raw:
            return self.get_response(request)

        domain, _port = split_domain_port(raw)
        if domain not in ('127.0.0.1', 'localhost', '::1'):
            return self.get_response(request)

        xf_raw = (request.META.get('HTTP_X_FORWARDED_HOST') or '').strip()
        if not xf_raw:
            return self.get_response(request)

        xf_first = xf_raw.split(',')[0].strip()
        xf_domain, _xf_port = split_domain_port(xf_first)
        if not xf_domain or not validate_host(xf_domain, settings.ALLOWED_HOSTS):
            return self.get_response(request)

        request.META['HTTP_HOST'] = xf_first
        return self.get_response(request)
