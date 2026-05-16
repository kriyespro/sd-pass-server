"""Unique slug/subdomain allocation for active (non-deleted) projects."""
from __future__ import annotations

import uuid

from django.utils.text import slugify

from .models import Project

_GENERIC_NAME_SLUGS = frozenset(
    {
        'my-portfolio',
        'my-portfolio-site',
        'my-site',
        'portfolio',
        'website',
        'project',
        'site',
        'home',
        'web',
    }
)


def _active_projects():
    return Project.objects.filter(is_deleted=False)


def user_slug_base(user) -> str:
    """Stable slug from email local-part or username (e.g. john.doe@school.edu → john-doe)."""
    email_local = ((getattr(user, 'email', None) or '').split('@')[0] or '').strip()
    raw = email_local or (getattr(user, 'username', None) or '').strip()
    base = slugify(raw.replace('.', '-').replace('_', '-')) if raw else ''
    if not base:
        first = (getattr(user, 'first_name', None) or '').strip()
        last = (getattr(user, 'last_name', None) or '').strip()
        base = slugify(f'{first}-{last}'.strip('-')) if (first or last) else ''
    return base or 'user'


def name_slug_base(name: str) -> str:
    return slugify((name or '').strip()) or 'project'


def suggest_subdomain_base(user, name: str = '') -> str:
    """
    Preferred subdomain stem before uniqueness suffixes.
    Uses username/email for generic project names; otherwise project name slug.
    """
    name_slug = name_slug_base(name)
    user_slug = user_slug_base(user)
    if name_slug in _GENERIC_NAME_SLUGS or len(name_slug) < 3:
        return user_slug
    if subdomain_is_available(name_slug):
        return name_slug
    combined = slugify(f'{user_slug}-{name_slug}')
    return combined or user_slug


def subdomain_is_available(sub: str, *, exclude_pk=None) -> bool:
    sub = (sub or '').strip().lower()
    if not sub:
        return False
    qs = _active_projects().filter(subdomain__iexact=sub)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return not qs.exists()


def slug_is_available(slug: str, *, exclude_pk=None) -> bool:
    slug = (slug or '').strip().lower()
    if not slug:
        return False
    qs = _active_projects().filter(slug__iexact=slug)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return not qs.exists()


def allocate_unique_subdomain(base: str, *, exclude_pk=None, max_suffix: int = 200) -> str:
    """Return base or base-1, base-2, … unique among active projects."""
    stem = slugify((base or '').strip()) or 'site'
    if len(stem) > 180:
        stem = stem[:180].rstrip('-')
    candidate = stem
    n = 1
    while not subdomain_is_available(candidate, exclude_pk=exclude_pk):
        suffix = f'-{n}'
        candidate = f'{stem[: 200 - len(suffix)]}{suffix}'.rstrip('-')
        n += 1
        if n > max_suffix:
            candidate = f'{stem[:160]}-{uuid.uuid4().hex[:10]}'
            break
    return candidate


def allocate_unique_slug(base: str, *, exclude_pk=None) -> str:
    """Return base or base-<uuid> unique among active projects."""
    stem = slugify((base or '').strip()) or 'project'
    candidate = stem
    if slug_is_available(candidate, exclude_pk=exclude_pk):
        return candidate
    return f'{stem[:180].rstrip("-")}-{uuid.uuid4().hex[:8]}'
