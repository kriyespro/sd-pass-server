"""Account lifecycle — deactivate instead of hard-delete from admin."""
from __future__ import annotations

import logging
import re

from django.contrib.sessions.models import Session
from django.utils import timezone

logger = logging.getLogger(__name__)


def profile_is_complete(user) -> bool:
    """Name, city, and mobile required before onboarding can advance past step 1."""
    if user is None:
        return False
    return bool(
        (user.first_name or '').strip()
        and (user.last_name or '').strip()
        and (user.mobile or '').strip()
        and (user.city or '').strip()
    )


def normalize_mobile(value: str) -> str:
    """Store digits with optional leading + for international numbers."""
    raw = (value or '').strip()
    digits = re.sub(r'\D', '', raw)
    if not digits:
        return ''
    if raw.startswith('+'):
        return f'+{digits}'
    return digits


def clear_user_sessions(user) -> int:
    """Log out all sessions for this user."""
    uid = str(user.pk)
    removed = 0
    for session in Session.objects.filter(expire_date__gte=timezone.now()).iterator():
        try:
            if session.get_decoded().get('_auth_user_id') == uid:
                session.delete()
                removed += 1
        except Exception:
            logger.exception('Failed to decode session %s', session.pk)
    return removed


def deactivate_user_account(user, *, clear_social: bool = True) -> None:
    """
    Deactivate a student account (admin action — not a hard delete).

    - Blocks future login (is_active=False)
    - Soft-deletes all projects (files, routes, subdomains freed)
    - Clears server sessions and Google linkage
    """
    from apps.projects.models import Project
    from apps.projects.services import soft_delete_project

    if user.is_superuser:
        raise ValueError('Cannot deactivate a superuser account.')

    for project in Project.objects.filter(owner=user, is_deleted=False):
        try:
            soft_delete_project(project=project, user=user)
        except Exception:
            logger.exception(
                'soft_delete_project failed for project %s (user %s)',
                project.pk,
                user.pk,
            )

    user.is_active = False
    user.save(update_fields=['is_active'])

    if clear_social:
        try:
            from allauth.socialaccount.models import SocialAccount

            SocialAccount.objects.filter(user=user).delete()
        except Exception:
            logger.exception('Failed to remove social accounts for user %s', user.pk)

    clear_user_sessions(user)
