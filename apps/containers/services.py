"""
HTTP client for the containers_runner sidecar (repo root, see php.txt section 3 INF-1).
That sidecar is the only process holding /var/run/docker.sock — this module never
imports the docker SDK. Same shape as apps/deployments/flask_runtime.py's client for
the flask-runner sidecar.
"""
from __future__ import annotations

import logging

import requests
from django.conf import settings

log = logging.getLogger(__name__)


def _runner_url() -> str:
    return getattr(settings, 'CONTAINERS_RUNNER_URL', 'http://containers-runner:6100')


def _headers() -> dict:
    token = getattr(settings, 'CONTAINERS_RUNNER_TOKEN', '')
    h = {'Content-Type': 'application/json'}
    if token:
        h['X-Runner-Token'] = token
    return h


# ── Naming ───────────────────────────────────────────────────────────────────────

def _name_prefix() -> str:
    """
    Optional prefix so multiple environments (e.g. a test deployment sharing a
    Docker host with production) never collide on container names — Docker
    requires container names to be unique per-host, and these are plain
    `proj_<pk>` strings with no environment scoping otherwise. Empty by default
    (unchanged behavior); set CONTAINER_NAME_PREFIX to something like 'test_'
    on a non-production deployment sharing a host with another one.
    """
    return getattr(settings, 'CONTAINER_NAME_PREFIX', '') or ''


def container_name(project) -> str:
    return f'{_name_prefix()}proj_{project.pk}'


def mysql_container_name(project) -> str:
    return f'{_name_prefix()}proj_{project.pk}_mysql'


# ── Suspend / unsuspend (php.txt Phase 5, BIL-1) ───────────────────────────────────

def suspend_project_containers(project) -> None:
    """docker stop the app + MySQL containers for a WORDPRESS/PHP/DRUPAL project.
    Data is preserved on their named volumes — this is not a de-provision."""
    from apps.databases.models import DatabaseInstance

    stop_container(container_name(project))
    if DatabaseInstance.objects.filter(project=project, engine=DatabaseInstance.Engine.MYSQL).exists():
        stop_container(mysql_container_name(project))


def unsuspend_project_containers(project) -> None:
    """docker start (no recreate) the app + MySQL containers for a WORDPRESS/PHP/DRUPAL
    project — reverses suspend_project_containers()."""
    from apps.databases.models import DatabaseInstance

    start_stopped_container(container_name(project))
    if DatabaseInstance.objects.filter(project=project, engine=DatabaseInstance.Engine.MYSQL).exists():
        start_stopped_container(mysql_container_name(project))


# ── Lifecycle ────────────────────────────────────────────────────────────────────

def start_container(
    name: str,
    image: str,
    env: dict[str, str] | None = None,
    volumes: dict[str, str] | None = None,
    mem_limit: str | None = None,
    nano_cpus: int | None = None,
    command: str | None = None,
) -> tuple[bool, str]:
    """
    Create (replacing any existing container of the same name) and start it.
    volumes is {volume_name: container_path} — named Docker volumes, not host paths.
    """
    payload: dict = {'image': image, 'env': env or {}, 'volumes': volumes or {}}
    if mem_limit:
        payload['mem_limit'] = mem_limit
    if nano_cpus:
        payload['nano_cpus'] = nano_cpus
    if command:
        payload['command'] = command
    try:
        resp = requests.post(
            f'{_runner_url()}/containers/{name}',
            json=payload,
            headers=_headers(),
            timeout=180,
        )
        data = resp.json()
        if resp.status_code == 200:
            return True, data.get('status', 'started')
        return False, data.get('error', f'HTTP {resp.status_code}')
    except requests.RequestException as exc:
        return False, f'containers-runner unreachable: {exc}'


def start_stopped_container(name: str) -> tuple[bool, str]:
    """Start an already-created (but stopped) container — no recreate. Used by health checks."""
    try:
        resp = requests.post(
            f'{_runner_url()}/containers/{name}/start',
            headers=_headers(),
            timeout=30,
        )
        data = resp.json()
        if resp.status_code == 200:
            return True, data.get('status', 'started')
        return False, data.get('error', f'HTTP {resp.status_code}')
    except requests.RequestException as exc:
        return False, f'containers-runner unreachable: {exc}'


def stop_container(name: str) -> None:
    try:
        requests.post(f'{_runner_url()}/containers/{name}/stop', headers=_headers(), timeout=30)
    except requests.RequestException as exc:
        log.warning('stop_container(%s) failed: %s', name, exc)


def remove_container(name: str, remove_volumes: bool = False) -> None:
    """remove_volumes=True also deletes any named volumes the sidecar attached under
    this container's name (e.g. '{name}_data') — use for a full de-provision, not a
    plain stop/replace."""
    try:
        requests.delete(
            f'{_runner_url()}/containers/{name}',
            params={'remove_volumes': 'true'} if remove_volumes else None,
            headers=_headers(),
            timeout=30,
        )
    except requests.RequestException as exc:
        log.warning('remove_container(%s) failed: %s', name, exc)


def upload_archive(name: str, tar_bytes: bytes, dest_path: str = '/var/www/html') -> tuple[bool, str]:
    """Extract a tar archive into an already-running container's filesystem (writes
    through to whatever volume is mounted at dest_path). Used to deploy PHP/Drupal
    site files into a project's own named volume — see php.txt section 5."""
    token = getattr(settings, 'CONTAINERS_RUNNER_TOKEN', '')
    headers = {'X-Runner-Token': token} if token else {}
    try:
        resp = requests.post(
            f'{_runner_url()}/containers/{name}/upload',
            params={'path': dest_path},
            data=tar_bytes,
            headers=headers,
            timeout=120,
        )
        data = resp.json()
        if resp.status_code == 200:
            return True, data.get('status', 'uploaded')
        return False, data.get('error', f'HTTP {resp.status_code}')
    except requests.RequestException as exc:
        return False, f'containers-runner unreachable: {exc}'


def container_status(name: str) -> dict:
    try:
        resp = requests.get(f'{_runner_url()}/containers/{name}/status', headers=_headers(), timeout=10)
        return resp.json()
    except requests.RequestException:
        return {'status': 'unknown'}


def container_is_running(name: str) -> bool:
    return container_status(name).get('status') == 'running'


def container_stats(name: str) -> dict:
    """Point-in-time mem/cpu usage for a running container — php.txt Phase 5, BIL-2.
    Returns {'status': 'running', 'mem_usage_mb', 'mem_limit_mb', 'cpu_percent'} or
    {'status': <not running/not found>} otherwise."""
    try:
        resp = requests.get(f'{_runner_url()}/containers/{name}/stats', headers=_headers(), timeout=10)
        return resp.json()
    except requests.RequestException:
        return {'status': 'unknown'}


def exec_in_container(name: str, cmd: list[str], timeout: int = 300) -> tuple[bool, str]:
    """Run a one-off command in an already-running container (composer install, drush, wp-cli)."""
    try:
        resp = requests.post(
            f'{_runner_url()}/containers/{name}/exec',
            json={'cmd': cmd},
            headers=_headers(),
            timeout=timeout + 10,
        )
        data = resp.json()
        if resp.status_code == 200:
            return data.get('exit_code', 1) == 0, data.get('output', '')
        return False, data.get('error', f'HTTP {resp.status_code}')
    except requests.RequestException as exc:
        return False, f'containers-runner unreachable: {exc}'


def runner_healthy() -> bool:
    try:
        resp = requests.get(f'{_runner_url()}/health', timeout=5)
        return resp.status_code == 200
    except requests.RequestException:
        return False
