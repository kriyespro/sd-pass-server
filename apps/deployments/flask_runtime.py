"""
Django-side client for the Flask Runner service.
Celery workers call these functions to deploy/stop/check student Flask and Django apps
(the runner process manages both the same way — venv + gunicorn per project).
"""
from __future__ import annotations

import logging

import requests
from django.conf import settings

log = logging.getLogger(__name__)

FLASK_PORT_START = 7000
FLASK_PORT_END   = 7999

DJANGO_PORT_START = 8000
DJANGO_PORT_END   = 8999


def _runner_url() -> str:
    return getattr(settings, 'FLASK_RUNNER_URL', 'http://flask-runner:6000')


def _headers() -> dict:
    token = getattr(settings, 'FLASK_RUNNER_TOKEN', '')
    h = {'Content-Type': 'application/json'}
    if token:
        h['X-Runner-Token'] = token
    return h


# ── Port allocation ───────────────────────────────────────────────────────────

def allocate_flask_port(project_id: int) -> int:
    """
    Return this project's already-allocated port, or allocate the next free one
    from FLASK_PORT_START..FLASK_PORT_END and persist it on the Project row.
    """
    from apps.projects.models import Project

    proj = Project.objects.filter(pk=project_id).only('flask_port').first()
    if proj and proj.flask_port:
        return proj.flask_port

    used: set[int] = set(
        Project.objects.filter(flask_port__isnull=False)
        .values_list('flask_port', flat=True)
    )
    for port in range(FLASK_PORT_START, FLASK_PORT_END + 1):
        if port not in used:
            Project.objects.filter(pk=project_id).update(flask_port=port)
            return port

    raise RuntimeError('Flask port pool exhausted (7000-7999 all in use).')


def free_flask_port(project_id: int) -> None:
    from apps.projects.models import Project
    Project.objects.filter(pk=project_id).update(flask_port=None)


def allocate_django_port(project_id: int) -> int:
    """
    Return this project's already-allocated port, or allocate the next free one
    from DJANGO_PORT_START..DJANGO_PORT_END and persist it on the Project row.
    """
    from apps.projects.models import Project

    proj = Project.objects.filter(pk=project_id).only('django_port').first()
    if proj and proj.django_port:
        return proj.django_port

    used: set[int] = set(
        Project.objects.filter(django_port__isnull=False)
        .values_list('django_port', flat=True)
    )
    for port in range(DJANGO_PORT_START, DJANGO_PORT_END + 1):
        if port not in used:
            Project.objects.filter(pk=project_id).update(django_port=port)
            return port

    raise RuntimeError('Django port pool exhausted (8000-8999 all in use).')


def free_django_port(project_id: int) -> None:
    from apps.projects.models import Project
    Project.objects.filter(pk=project_id).update(django_port=None)


# ── Runner API calls ──────────────────────────────────────────────────────────

def runner_deploy(
    project_id: int, port: int, project_type: str = 'flask', env: dict[str, str] | None = None,
) -> tuple[bool, str]:
    """
    Ask the runner to (re)start the app (Flask or Django).
    Returns (True, entry_point) on success or (False, error_msg).
    Blocks until pip install (+ migrate for Django) + gunicorn start completes (up to ~4 min).
    `env` (e.g. DATABASE_URL for Django) is injected into the app's process environment.
    """
    try:
        resp = requests.post(
            f'{_runner_url()}/deploy/{project_id}',
            json={'port': port, 'project_type': project_type, 'env': env or {}},
            headers=_headers(),
            timeout=300,
        )
        data = resp.json()
        if resp.status_code == 200:
            return True, data.get('entry', 'app:app')
        return False, data.get('error', f'HTTP {resp.status_code}')
    except requests.RequestException as exc:
        return False, f'runner unreachable: {exc}'


def runner_stop(project_id: int) -> None:
    try:
        requests.post(
            f'{_runner_url()}/stop/{project_id}',
            headers=_headers(),
            timeout=10,
        )
    except requests.RequestException as exc:
        log.warning('runner_stop(%s) failed: %s', project_id, exc)


def runner_set_django_superuser(
    project_id: int, username: str, email: str, password: str, env: dict[str, str] | None = None,
) -> tuple[bool, str]:
    """
    Create or reset a Django superuser (is_staff + is_superuser) directly in the
    project's own database. Returns (True, 'created'|'updated') or (False, error_msg).
    """
    try:
        resp = requests.post(
            f'{_runner_url()}/django_superuser/{project_id}',
            json={'username': username, 'email': email, 'password': password, 'env': env or {}},
            headers=_headers(),
            timeout=60,
        )
        data = resp.json()
        if resp.status_code == 200:
            return True, data.get('action', 'updated')
        return False, data.get('error', f'HTTP {resp.status_code}')
    except requests.RequestException as exc:
        return False, f'runner unreachable: {exc}'


def runner_status(project_id: int) -> dict:
    try:
        resp = requests.get(
            f'{_runner_url()}/status/{project_id}',
            headers=_headers(),
            timeout=5,
        )
        return resp.json()
    except requests.RequestException:
        return {'status': 'unknown'}


def runner_healthy() -> bool:
    try:
        resp = requests.get(f'{_runner_url()}/health', timeout=5)
        return resp.status_code == 200
    except requests.RequestException:
        return False
