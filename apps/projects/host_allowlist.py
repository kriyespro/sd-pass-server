"""Trust Project.custom_hostname for Host / CSRF without editing server env each time."""
from __future__ import annotations

from django.core.cache import cache

from apps.projects.models import Project

_CACHE_PREFIX = 'projects:allow_host:'
_CACHE_PREFIX_VERIFIED = 'projects:allow_host_verified:'
_CACHE_TTL = 600


def invalidate_custom_host_cache(hostname: str | None) -> None:
    if not hostname:
        return
    h = hostname.strip().lower().rstrip('.')
    cache.delete(_CACHE_PREFIX + h)
    cache.delete(_CACHE_PREFIX_VERIFIED + h)


def project_has_custom_hostname(host: str) -> bool:
    """Any active project claims this hostname (verified or pending verification)."""
    h = host.strip().lower().rstrip('.')
    if not h:
        return False
    key = _CACHE_PREFIX + h
    hit = cache.get(key)
    if hit is not None:
        return bool(hit)
    ok = Project.objects.filter(custom_hostname__iexact=h, is_deleted=False).exists()
    cache.set(key, ok, _CACHE_TTL)
    return ok


def is_trusted_custom_hostname(host: str) -> bool:
    """
    True if host matches an active project's custom_hostname and DNS TXT is verified.
    """
    h = host.strip().lower().rstrip('.')
    if not h:
        return False
    key = _CACHE_PREFIX_VERIFIED + h
    hit = cache.get(key)
    if hit is not None:
        return bool(hit)
    ok = Project.objects.filter(
        custom_hostname__iexact=h,
        is_deleted=False,
        custom_hostname_verified=True,
    ).exists()
    cache.set(key, ok, _CACHE_TTL)
    return ok


def _ensure_mutable_sequence(setting_name: str) -> list:
    from django.conf import settings

    cur = getattr(settings, setting_name)
    if isinstance(cur, tuple):
        cur = list(cur)
        setattr(settings, setting_name, cur)
    elif cur is None:
        cur = []
        setattr(settings, setting_name, cur)
    return cur


def register_host_for_django(host: str, *, trust_csrf: bool = True) -> None:
    """
    Append host to ALLOWED_HOSTS. Optionally append CSRF_TRUSTED_ORIGINS
    (omit for custom domains that are not yet TXT-verified).
    """
    from django.conf import settings

    h = host.strip().lower().rstrip('.')
    if not h:
        return

    allowed = _ensure_mutable_sequence('ALLOWED_HOSTS')
    if h not in allowed:
        allowed.append(h)

    if not trust_csrf:
        return

    origins = _ensure_mutable_sequence('CSRF_TRUSTED_ORIGINS')
    for origin in (f'https://{h}', f'http://{h}'):
        if origin not in origins:
            origins.append(origin)

    if getattr(settings, 'STUDENT_PUBLIC_HTTP_PORT', 0):
        try:
            port = int(settings.STUDENT_PUBLIC_HTTP_PORT)
        except (TypeError, ValueError):
            port = 0
        if port:
            for scheme in ('http', 'https'):
                o = f'{scheme}://{h}:{port}'
                if o not in origins:
                    origins.append(o)
