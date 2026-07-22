"""Trust Project.custom_hostname for Host / CSRF without editing server env each time.

Also treats ``www.example.com`` and ``example.com`` as the same custom domain so
visitors do not hit Django DisallowedHost (HTTP 400) when only one form was saved.
"""
from __future__ import annotations

from django.core.cache import cache
from django.db.models import Q

from apps.projects.models import Project

_CACHE_PREFIX = 'projects:allow_host:v2:'
_CACHE_PREFIX_VERIFIED = 'projects:allow_host_verified:v2:'
_CACHE_TTL = 600
_CACHE_TTL_MISS = 30  # short negative cache so DNS/sibling fixes apply quickly


def normalize_hostname(host: str | None) -> str:
    return (host or '').strip().lower().rstrip('.')


def host_without_port(raw: str) -> str:
    """
    Host part of HTTP Host header. Do not use split(':')[0] — it breaks
    ``radha.example.com:9898`` into ``radha`` instead of ``radha.example.com``.
    """
    raw = (raw or '').strip()
    if not raw:
        return ''
    if raw.startswith('['):
        end = raw.find(']')
        if end != -1 and len(raw) > end + 1 and raw[end + 1] == ':':
            return raw[: end + 1].lower()
        return raw.lower()
    if ':' in raw:
        host, maybe_port = raw.rsplit(':', 1)
        if maybe_port.isdigit():
            return host.lower()
    return raw.lower()


def sibling_hostname(host: str | None) -> str | None:
    """
    Return the www ↔ apex sibling for a hostname, or None if not applicable.

    ``example.com`` ↔ ``www.example.com``
    """
    h = normalize_hostname(host)
    if not h or '.' not in h:
        return None
    if h.startswith('www.'):
        rest = h[4:]
        # Need at least one dot in the remainder (e.g. example.com), not bare TLD.
        if rest and '.' in rest:
            return rest
        return None
    return f'www.{h}'


def hostname_aliases(host: str | None) -> frozenset[str]:
    """Exact host plus its www/apex sibling (when applicable)."""
    h = normalize_hostname(host)
    if not h:
        return frozenset()
    sib = sibling_hostname(h)
    return frozenset({h, sib}) if sib else frozenset({h})


def invalidate_custom_host_cache(hostname: str | None) -> None:
    if not hostname:
        return
    for alias in hostname_aliases(hostname):
        cache.delete(_CACHE_PREFIX + alias)
        cache.delete(_CACHE_PREFIX_VERIFIED + alias)


def _custom_host_q(host: str) -> Q:
    """Match stored custom_hostname against host or its www/apex sibling."""
    q = Q()
    for alias in hostname_aliases(host):
        q |= Q(custom_hostname__iexact=alias)
    return q


def project_has_custom_hostname(host: str) -> bool:
    """Any active project claims this hostname (verified or pending), incl. www↔apex."""
    h = normalize_hostname(host)
    if not h:
        return False
    key = _CACHE_PREFIX + h
    hit = cache.get(key)
    if hit is not None:
        return bool(hit)
    ok = Project.objects.filter(_custom_host_q(h), is_deleted=False).exists()
    ttl = _CACHE_TTL if ok else _CACHE_TTL_MISS
    cache.set(key, ok, ttl)
    # Warm sibling cache too so the other form does not re-query immediately.
    sib = sibling_hostname(h)
    if sib:
        cache.set(_CACHE_PREFIX + sib, ok, ttl)
    return ok


def is_trusted_custom_hostname(host: str) -> bool:
    """
    True if host (or its www/apex sibling) matches an active project's
    custom_hostname and DNS TXT is verified.
    """
    h = normalize_hostname(host)
    if not h:
        return False
    key = _CACHE_PREFIX_VERIFIED + h
    hit = cache.get(key)
    if hit is not None:
        return bool(hit)
    ok = Project.objects.filter(
        _custom_host_q(h),
        is_deleted=False,
        custom_hostname_verified=True,
    ).exists()
    ttl = _CACHE_TTL if ok else _CACHE_TTL_MISS
    cache.set(key, ok, ttl)
    sib = sibling_hostname(h)
    if sib:
        cache.set(_CACHE_PREFIX_VERIFIED + sib, ok, ttl)
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
    Append host (and www/apex sibling) to ALLOWED_HOSTS.
    Optionally append CSRF_TRUSTED_ORIGINS (omit until TXT-verified).
    """
    from django.conf import settings

    aliases = hostname_aliases(host)
    if not aliases:
        return

    allowed = _ensure_mutable_sequence('ALLOWED_HOSTS')
    for h in aliases:
        if h not in allowed:
            allowed.append(h)

    if not trust_csrf:
        return

    origins = _ensure_mutable_sequence('CSRF_TRUSTED_ORIGINS')
    for h in aliases:
        for origin in (f'https://{h}', f'http://{h}'):
            if origin not in origins:
                origins.append(origin)

    if getattr(settings, 'STUDENT_PUBLIC_HTTP_PORT', 0):
        try:
            port = int(settings.STUDENT_PUBLIC_HTTP_PORT)
        except (TypeError, ValueError):
            port = 0
        if port:
            for h in aliases:
                for scheme in ('http', 'https'):
                    o = f'{scheme}://{h}:{port}'
                    if o not in origins:
                        origins.append(o)
